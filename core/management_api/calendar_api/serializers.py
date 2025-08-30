"""Serializers for Calendar API"""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Calendar


class CalendarSerializer(serializers.ModelSerializer):
    """Serializer for Calendar model with provider details"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    provider_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Calendar
        fields = [
            'id', 'workspace', 'workspace_name', 'name', 'provider', 
            'active', 'provider_details',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.DictField)
    def get_provider_details(self, obj):
        """Get provider-specific details"""
        if obj.provider == 'google' and hasattr(obj, 'google_calendar'):
            google_cal = obj.google_calendar
            return {
                'external_id': google_cal.external_id,
                'account_email': google_cal.account_email,
                'time_zone': google_cal.time_zone,
                'access_role': google_cal.access_role,
            }
        elif obj.provider == 'outlook' and hasattr(obj, 'outlook_calendar'):
            outlook_cal = obj.outlook_calendar
            return {
                'external_id': outlook_cal.external_id,
                'primary_email': outlook_cal.primary_email,
                'display_name': outlook_cal.display_name,
                'timezone_windows': outlook_cal.timezone_windows,
                'can_edit': outlook_cal.can_edit,
            }
        return None
    
    # Removed misleading connection_status field


class CalendarSubAccountSerializer(serializers.Serializer):
    """Lightweight, provider-agnostic sub-account representation for a calendar"""
    id = serializers.UUIDField()
    provider = serializers.ChoiceField(choices=['google', 'outlook'])
    address = serializers.CharField(help_text="Email/UPN or calendar identifier")
    calendar_name = serializers.CharField(allow_blank=True, required=False)
    relationship = serializers.CharField()
    is_default = serializers.BooleanField()