"""Serializers for Calendar API"""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Calendar


class CalendarSerializer(serializers.ModelSerializer):
    """Serializer for Calendar model with provider details"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    provider_details = serializers.SerializerMethodField()
    connection_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Calendar
        fields = [
            'id', 'workspace', 'workspace_name', 'name', 'provider', 
            'active', 'provider_details', 'connection_status',
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
    
    @extend_schema_field(serializers.CharField)
    def get_connection_status(self, obj):
        """Get connection status based on provider"""
        if obj.provider == 'google' and hasattr(obj, 'google_calendar'):
            google_cal = obj.google_calendar
            if google_cal.sync_errors:
                return 'error'
            elif google_cal.last_sync:
                return 'connected'
            else:
                return 'pending'
        elif obj.provider == 'outlook' and hasattr(obj, 'outlook_calendar'):
            outlook_cal = obj.outlook_calendar
            if outlook_cal.sync_errors:
                return 'error'
            elif outlook_cal.last_sync:
                return 'connected'
            else:
                return 'pending'
        return 'disconnected'