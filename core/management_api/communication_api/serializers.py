from rest_framework import serializers


class SendDocumentRequestSerializer(serializers.Serializer):
    """
    Request serializer for sending agent document to lead via email.
    
    This endpoint sends a configured PDF document from an agent to a lead's email
    using the workspace SMTP settings and agent's configured email defaults.
    """
    agent_id = serializers.CharField(
        required=True,
        help_text="The ID of the agent whose document will be sent"
    )
    lead_id = serializers.CharField(
        required=True,
        help_text="The ID of the lead who will receive the document"
    )


class SendDocumentResponseSerializer(serializers.Serializer):
    """Response serializer for send document endpoint"""
    success = serializers.BooleanField(
        help_text="Indicates if the document was sent successfully"
    )
    error = serializers.CharField(
        required=False,
        help_text="Error message if sending failed"
    )