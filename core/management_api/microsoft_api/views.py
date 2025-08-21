import logging
import requests
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from core.models import MicrosoftSubscription, MicrosoftCalendarConnection  # type: ignore

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class MicrosoftWebhookView(viewsets.ViewSet):
    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(summary="Microsoft webhook validation (Graph validationToken)")
    def verify(self, request):
        token = request.GET.get('validationToken')
        if token:
            # Echo the token as plain text with 200 OK per Graph spec
            return HttpResponse(token, content_type='text/plain', status=200)
        return Response('OK')

    @extend_schema(summary="Microsoft webhook notification handler")
    def notify(self, request):
        try:
            data = request.data or {}
            # Verify clientState
            notifications = data.get('value', []) if isinstance(data, dict) else []
            for n in notifications:
                sub_id = n.get('subscriptionId')
                client_state = n.get('clientState')
                try:
                    sub = MicrosoftSubscription.objects.select_related('connection').get(subscription_id=sub_id)
                except MicrosoftSubscription.DoesNotExist:
                    logger.warning("Unknown Microsoft subscription: %s", sub_id)
                    continue
                if sub.client_state and client_state and sub.client_state != client_state:
                    logger.warning("ClientState mismatch for subscription %s", sub_id)
                    continue
                # Fetch event by ID if provided
                resource = n.get('resourceData', {})
                event_id = resource.get('id')
                if event_id:
                    try:
                        headers = {'Authorization': f'Bearer {sub.connection.access_token}'}
                        resp = requests.get(f'https://graph.microsoft.com/v1.0/me/events/{event_id}', headers=headers, timeout=30)
                        if resp.status_code == 200:
                            logger.info("Fetched event %s for subscription %s", event_id, sub_id)
                        else:
                            logger.warning("Failed to fetch event %s: %s", event_id, resp.status_code)
                    except Exception as e:
                        logger.error("Error fetching event %s: %s", event_id, str(e))
                        continue
            return Response({"status": "received"})
        except Exception as e:
            logger.error(f"Microsoft webhook handling failed: {str(e)}")
            return Response({"error": "failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


