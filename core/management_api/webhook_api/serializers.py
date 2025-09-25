from rest_framework import serializers
from core.models import WebhookLeadSource, LeadFunnel


class WebhookLeadIncomeRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    surname = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=50)
    email = serializers.EmailField()

    # Collect all additional fields in variables
    variables = serializers.DictField(required=False)

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)

        variables = {k: v for k, v in data.items() if k not in self.fields}
        validated["variables"] = variables
        return validated

class WebhookCreateRequestSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    webhook_name = serializers.CharField(max_length=255)
    variables = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
        default=list,
        help_text="List of variable names for the webhook"
    )

    def validate_variables(self, value):
        """Validate that all variables are valid strings"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Variables must be a list")

        for var in value:
            if not isinstance(var, str) or not var.strip():
                raise serializers.ValidationError("All variables must be non-empty strings")

        return value


class WebhookCreateResponseSerializer(serializers.Serializer):
    webhook_id = serializers.UUIDField()
    webhook_name = serializers.CharField()
    lead_funnel_id = serializers.UUIDField()
    webhook_url = serializers.URLField()
    secret_token = serializers.CharField()
    public_key = serializers.CharField()
    required_headers = serializers.DictField()


class WebhookDeleteRequestSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    webhook_id = serializers.UUIDField()


class WebhookDeleteResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['success', 'error'])
    message = serializers.CharField()


class WebhookGetRequestSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    webhook_id = serializers.UUIDField()


class WebhookGetResponseSerializer(serializers.Serializer):
    webhook_name = serializers.CharField()
    webhook_id = serializers.UUIDField()
    public_key = serializers.CharField()
    token = serializers.CharField()
    has_lead_funnel = serializers.BooleanField()


class WebhookRefreshTokenRequestSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    webhook_id = serializers.UUIDField()


class WebhookRefreshTokenResponseSerializer(serializers.Serializer):
    webhook_id = serializers.UUIDField()
    token = serializers.CharField()


class WebhookLeadIncomeResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['success', 'error'])
    message = serializers.CharField()
