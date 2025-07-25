from rest_framework import serializers
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
    
    def get_full_name(self, obj):
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