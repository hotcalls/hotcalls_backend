from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Lead


class LeadSerializer(serializers.ModelSerializer):
    """Serializer for Lead model"""
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'name', 'surname', 'full_name', 'email', 'phone', 
            'meta_data', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.CharField)
    def get_full_name(self, obj) -> str:
        """Get the full name of the lead"""
        if obj.surname:
            return f"{obj.name} {obj.surname}"
        return obj.name


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