from datetime import datetime

from django.core.mail import EmailMessage, get_connection
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.models import Agent, Lead
from core.management_api.communication_api.permissions import LiveKitOrAuthenticatedWorkspaceUser
from core.management_api.communication_api.serializers import (
    SendDocumentRequestSerializer,
    SendDocumentResponseSerializer
)
from core.utils.crypto import decrypt_text


class CommunicationViewSet(viewsets.ViewSet):
    permission_classes = [LiveKitOrAuthenticatedWorkspaceUser]

    @extend_schema(
        summary="📄 Send agent document to lead",
        description="""
        Send the configured agent PDF document to a lead's email using the workspace SMTP settings.
        
        **Requirements:**
        - Agent must have a PDF document configured
        - Lead must have a valid email address
        - Agent and lead must belong to the same workspace
        - Workspace must have SMTP enabled and configured
        
        **Email Content:**
        - Uses agent's configured email_default_subject and email_default_body
        - Supports placeholders in body: {current_date}, {lead_name}
        
        **Authentication:** None required (AllowAny)
        """,
        tags=["Communication"],
        request=SendDocumentRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=SendDocumentResponseSerializer,
                description="✅ Document sent successfully"
            ),
            400: OpenApiResponse(description="❌ Bad request - missing parameters or configuration issues"),
            403: OpenApiResponse(description="❌ Forbidden - agent and lead not in same workspace"),
            404: OpenApiResponse(description="❌ Agent or lead not found")
        },
        auth=[]
    )
    @action(detail=False, methods=['post'], url_path='send-document', permission_classes=[AllowAny])
    def send_document(self, request):
        agent_id = request.data.get('agent_id')
        lead_id = request.data.get('lead_id')

        if not agent_id or not lead_id:
            return Response({'error': 'agent_id and lead_id are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            agent = Agent.objects.select_related('workspace').get(agent_id=agent_id)
        except Agent.DoesNotExist:
            return Response({'error': 'Agent not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            lead = Lead.objects.select_related('workspace').get(id=lead_id)
        except Lead.DoesNotExist:
            return Response({'error': 'Lead not found'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure same workspace and email present
        if not (lead.workspace and agent.workspace and lead.workspace == agent.workspace):
            return Response({'error': 'Agent and Lead must belong to the same workspace'}, status=status.HTTP_403_FORBIDDEN)
        if not lead.email:
            return Response({'error': 'Lead has no email address'}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure document exists
        if not agent.send_document:
            return Response({'error': 'Agent has no send-document configured'}, status=status.HTTP_400_BAD_REQUEST)

        workspace = agent.workspace
        # Strict policy: must have workspace SMTP configured and enabled
        if not workspace.smtp_enabled:
            return Response({'error': 'Workspace SMTP is not enabled'}, status=status.HTTP_400_BAD_REQUEST)
        if not (workspace.smtp_host and workspace.smtp_from_email):
            return Response({'error': 'Incomplete workspace SMTP configuration'}, status=status.HTTP_400_BAD_REQUEST)

        # Build subject/body from agent defaults with workspace fallbacks
        subject = (agent.email_default_subject or f"Ihre Informationen von {workspace.workspace_name}")
        # Allowed placeholders: {current_date}, {lead_name}
        lead_name = (lead.name or '').strip()
        current_date = datetime.now().strftime('%Y-%m-%d')
        body_base = (agent.email_default_body or f"Hallo {lead_name}, anbei die Unterlagen. Viele Grüße")
        body = body_base.replace('{current_date}', current_date).replace('{lead_name}', lead_name)

        # Build SMTP connection
        password = decrypt_text(workspace.smtp_password_encrypted) or ''
        try:
            conn = get_connection(
                host=workspace.smtp_host,
                port=workspace.smtp_port,
                username=workspace.smtp_username or None,
                password=password or None,
                use_tls=workspace.smtp_use_tls,
                use_ssl=workspace.smtp_use_ssl,
            )
        except Exception as e:
            return Response({'error': f'Failed to create SMTP connection: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            msg = EmailMessage(
                subject=subject,
                body=body,
                from_email=workspace.smtp_from_email,
                to=[lead.email],
                connection=conn,
            )
            # Attach the PDF
            file_field = agent.send_document
            file_field.open('rb')
            try:
                msg.attach(filename=file_field.name.split('/')[-1], content=file_field.read(), mimetype='application/pdf')
            finally:
                file_field.close()
            msg.send(fail_silently=False)
            return Response({'success': True})
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


