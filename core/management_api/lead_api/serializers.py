from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Lead, INTEGRATION_PROVIDER_CHOICES


class LeadSerializer(serializers.ModelSerializer):
    """Serializer for Lead model"""
    full_name = serializers.SerializerMethodField()
    workspace_name = serializers.SerializerMethodField()
    integration_provider_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'name', 'surname', 'full_name', 'email', 'phone', 
            'workspace', 'workspace_name', 'integration_provider', 
            'integration_provider_display', 'variables', 'meta_data', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'full_name', 'workspace_name', 'integration_provider_display']
    
    @extend_schema_field(serializers.CharField)
    def get_full_name(self, obj) -> str:
        """Get the full name of the lead"""
        if obj.surname:
            return f"{obj.name} {obj.surname}"
        return obj.name
    
    @extend_schema_field(serializers.CharField)
    def get_workspace_name(self, obj) -> str:
        """Get the workspace name"""
        return obj.workspace.workspace_name if obj.workspace else None
    
    @extend_schema_field(serializers.CharField)
    def get_integration_provider_display(self, obj) -> str:
        """Get the human-readable integration provider name"""
        if obj.integration_provider:
            provider_dict = dict(INTEGRATION_PROVIDER_CHOICES)
            return provider_dict.get(obj.integration_provider, obj.integration_provider)
        return None


class LeadCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating leads"""
    
    class Meta:
        model = Lead
        fields = ['name', 'surname', 'email', 'phone', 'meta_data']


class LeadUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating leads"""
    
    class Meta:
        model = Lead
        fields = ['name', 'surname', 'email', 'phone', 'meta_data']


class LeadBulkCreateSerializer(serializers.Serializer):
    """Serializer for bulk creating leads"""
    leads = serializers.ListField(
        child=LeadCreateSerializer(),
        help_text="List of leads to create"
    )
    
    def create(self, validated_data):
        """Create multiple leads"""
        leads_data = validated_data['leads']
        leads = []
        
        for lead_data in leads_data:
            lead = Lead.objects.create(**lead_data)
            leads.append(lead)
        
        return leads


class LeadMetaDataUpdateSerializer(serializers.Serializer):
    """Serializer for updating lead metadata"""
    meta_data = serializers.JSONField(help_text="Custom JSON metadata for the lead")
    
    def validate_meta_data(self, value):
        """Validate that meta_data is a valid JSON object"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("meta_data must be a JSON object")
        return value


class LeadStatsSerializer(serializers.Serializer):
    """Serializer for lead statistics"""
    total_leads = serializers.IntegerField(read_only=True)
    leads_with_calls = serializers.IntegerField(read_only=True)
    leads_without_calls = serializers.IntegerField(read_only=True)
    avg_calls_per_lead = serializers.FloatField(read_only=True, allow_null=True)


class MetaLeadSerializer(serializers.ModelSerializer):
    """Serializer for Meta-sourced leads"""
    full_name = serializers.SerializerMethodField()
    workspace_name = serializers.SerializerMethodField()
    meta_lead_forms = serializers.SerializerMethodField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'name', 'surname', 'full_name', 'email', 'phone', 'workspace',
            'workspace_name', 'integration_provider', 'variables', 'meta_data',
            'meta_lead_forms', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'full_name', 'workspace_name', 'meta_lead_forms']
    
    @extend_schema_field(serializers.CharField)
    def get_full_name(self, obj) -> str:
        """Get the full name of the lead"""
        if obj.surname:
            return f"{obj.name} {obj.surname}"
        return obj.name
    
    @extend_schema_field(serializers.CharField)
    def get_workspace_name(self, obj) -> str:
        """Get the workspace name"""
        return obj.workspace.workspace_name if obj.workspace else None
    
    @extend_schema_field(serializers.ListField)
    def get_meta_lead_forms(self, obj) -> list:
        """Get associated Meta lead forms"""
        return [
            {
                'id': str(form.id),
                'meta_form_id': form.meta_form_id,
                'meta_lead_id': form.meta_lead_id,
                'integration_id': str(form.meta_integration.id)
            }
            for form in obj.meta_lead_forms.all()
        ]


class LeadIntegrationFilterSerializer(serializers.Serializer):
    """Serializer for filtering leads by integration"""
    integration_provider = serializers.ChoiceField(
        choices=INTEGRATION_PROVIDER_CHOICES,
        required=False,
        help_text="Filter by integration provider"
    )
    workspace = serializers.UUIDField(
        required=False,
        help_text="Filter by workspace ID"
    )
    has_variables = serializers.BooleanField(
        required=False,
        help_text="Filter leads that have integration variables"
    ) 