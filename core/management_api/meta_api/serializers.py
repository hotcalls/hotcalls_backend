from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import MetaIntegration, MetaLeadForm, Lead, Workspace


class MetaIntegrationSerializer(serializers.ModelSerializer):
    """Serializer for Meta Integration"""
    workspace_name = serializers.SerializerMethodField()
    lead_forms_count = serializers.SerializerMethodField()
    
    class Meta:
        model = MetaIntegration
        fields = [
            'id', 'workspace', 'workspace_name', 'business_account_id', 'page_id',
            'access_token_expires_at', 'scopes', 'status', 'lead_forms_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'workspace_name', 'lead_forms_count']
        extra_kwargs = {
            'access_token': {'write_only': True},  # Never expose in responses
            'verification_token': {'write_only': True}  # Never expose in responses
        }
    
    @extend_schema_field(serializers.CharField)
    def get_workspace_name(self, obj) -> str:
        """Get the workspace name"""
        return obj.workspace.workspace_name if obj.workspace else None
    
    @extend_schema_field(serializers.IntegerField)
    def get_lead_forms_count(self, obj) -> int:
        """Get the count of lead forms for this integration"""
        return obj.lead_forms.count()


class MetaIntegrationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Meta integrations"""
    
    class Meta:
        model = MetaIntegration
        fields = [
            'workspace', 'business_account_id', 'page_id', 'access_token',
            'access_token_expires_at', 'verification_token', 'scopes'
        ]


class MetaLeadFormSerializer(serializers.ModelSerializer):
    """Serializer for Meta Lead Form"""
    workspace = serializers.SerializerMethodField()
    integration_status = serializers.SerializerMethodField()
    lead_count = serializers.SerializerMethodField()
    
    class Meta:
        model = MetaLeadForm
        fields = [
            'id', 'meta_integration', 'workspace', 'meta_form_id', 'meta_lead_id',
            'variables_scheme', 'lead', 'integration_status', 'lead_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'workspace', 'integration_status', 'lead_count']
    
    @extend_schema_field(serializers.UUIDField)
    def get_workspace(self, obj):
        """Get the workspace ID"""
        return obj.meta_integration.workspace.id if obj.meta_integration.workspace else None
    
    @extend_schema_field(serializers.CharField)
    def get_integration_status(self, obj) -> str:
        """Get the integration status"""
        return obj.meta_integration.status
    
    @extend_schema_field(serializers.IntegerField)
    def get_lead_count(self, obj) -> int:
        """Get count of leads created from this form"""
        return MetaLeadForm.objects.filter(meta_form_id=obj.meta_form_id).count()


class MetaLeadFormCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Meta lead forms"""
    
    class Meta:
        model = MetaLeadForm
        fields = ['meta_integration', 'meta_form_id', 'variables_scheme']


class MetaOAuthCallbackSerializer(serializers.Serializer):
    """Serializer for Meta OAuth callback"""
    code = serializers.CharField(
        help_text="Authorization code from Meta"
    )
    state = serializers.CharField(
        help_text="State parameter for CSRF protection",
        required=False
    )
    workspace_id = serializers.UUIDField(
        help_text="Workspace ID to associate the integration with"
    )


class MetaLeadWebhookSerializer(serializers.Serializer):
    """Serializer for Meta lead webhook data"""
    object = serializers.CharField()
    entry = serializers.ListField(
        child=serializers.DictField(),
        help_text="Array of webhook entries from Meta"
    )
    
    def validate_object(self, value):
        """Validate that the webhook is for lead forms"""
        if value != 'page':
            raise serializers.ValidationError("Only page webhook events are supported")
        return value


class MetaWebhookVerificationSerializer(serializers.Serializer):
    """Serializer for Meta webhook verification"""
    hub_mode = serializers.CharField(source='hub.mode')
    hub_challenge = serializers.CharField(source='hub.challenge') 
    hub_verify_token = serializers.CharField(source='hub.verify_token')


class MetaLeadDataSerializer(serializers.Serializer):
    """Serializer for processing Meta lead data"""
    leadgen_id = serializers.CharField(help_text="Meta lead ID")
    page_id = serializers.CharField(help_text="Meta page ID")
    form_id = serializers.CharField(help_text="Meta form ID")
    adgroup_id = serializers.CharField(required=False)
    ad_id = serializers.CharField(required=False)
    created_time = serializers.DateTimeField()
    field_data = serializers.ListField(
        child=serializers.DictField(),
        help_text="Lead form field data"
    )


class MetaIntegrationStatsSerializer(serializers.Serializer):
    """Serializer for Meta integration statistics"""
    total_integrations = serializers.IntegerField(read_only=True)
    active_integrations = serializers.IntegerField(read_only=True)
    total_lead_forms = serializers.IntegerField(read_only=True)
    total_leads_received = serializers.IntegerField(read_only=True)
    leads_this_month = serializers.IntegerField(read_only=True)
    top_performing_forms = serializers.ListField(read_only=True) 