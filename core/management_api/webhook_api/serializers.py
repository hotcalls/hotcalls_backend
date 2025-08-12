from rest_framework import serializers
from core.models import WebhookLeadSource, LeadFunnel


class WebhookLeadPayloadSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=50)
    surname = serializers.CharField(max_length=255, required=False, allow_blank=True)
    variables = serializers.DictField(required=False)
    external_id = serializers.CharField(required=False, allow_blank=True)


class WebhookLeadSourceCreateSerializer(serializers.ModelSerializer):
    workspace = serializers.UUIDField(write_only=True)
    name = serializers.CharField(max_length=255)

    class Meta:
        model = WebhookLeadSource
        fields = ['workspace', 'name']


class WebhookLeadSourceSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    required_headers = serializers.SerializerMethodField()
    lead_funnel = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = WebhookLeadSource
        fields = ['id', 'name', 'url', 'lead_funnel', 'created_at', 'updated_at', 'required_headers']
        read_only_fields = ['id', 'url', 'lead_funnel', 'created_at', 'updated_at', 'required_headers']

    def get_url(self, obj: WebhookLeadSource):
        request = self.context.get('request')
        if request:
            # Force HTTPS for external webhook URLs since nginx enforces SSL redirect
            base = request.build_absolute_uri('/')
            # Replace http:// with https:// to match nginx SSL enforcement
            if base.startswith('http://'):
                base = base.replace('http://', 'https://', 1)
            base = base.rstrip('/')
        else:
            # Fallback if no request context
            base = 'https://app.hotcalls.de'
        return f"{base}/api/webhooks/leads/{obj.public_key}/"

    def get_required_headers(self, obj: WebhookLeadSource):
        return {
            'Authorization': 'Bearer <token>'
        }


