import logging
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class MicrosoftWebhookView(viewsets.ViewSet):
    """
    Minimal webhook endpoint for Microsoft Graph.
    Since we're OAuth-only, this just handles verification.
    """
    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(summary="Microsoft webhook validation (Graph validationToken)")
    def verify(self, request):
        """Handle Microsoft Graph webhook verification"""
        token = request.GET.get('validationToken')
        if token:
            # Echo the token as plain text with 200 OK per Graph spec
            return HttpResponse(token, content_type='text/plain', status=200)
        return Response('OK')

    @extend_schema(summary="Microsoft webhook notification handler")
    def notify(self, request):
        """
        Handle webhook notifications.
        Since we're OAuth-only, we just acknowledge receipt.
        """
        # Just acknowledge the webhook
        logger.info("Received Microsoft webhook notification")
        return Response({"status": "received"})