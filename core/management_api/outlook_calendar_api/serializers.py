"""Serializers for Outlook Calendar API"""
from rest_framework import serializers
from core.models import OutlookCalendar, Calendar


class OutlookCalendarSerializer(serializers.ModelSerializer):
    """Serializer for OutlookCalendar model"""
    calendar_name = serializers.CharField(source='calendar.name', read_only=True)
    workspace_id = serializers.UUIDField(source='calendar.workspace.id', read_only=True)
    workspace_name = serializers.CharField(source='calendar.workspace.workspace_name', read_only=True)
    is_token_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = OutlookCalendar
        fields = [
            'id', 'calendar', 'calendar_name', 'workspace_id', 'workspace_name',
            'user', 'primary_email', 'tenant_id', 'ms_user_id', 'display_name',
            'timezone_windows', 'external_id', 'can_edit', 'token_expires_at',
            'is_token_expired', 'scopes_granted', 'last_sync', 'sync_errors',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'tenant_id', 'ms_user_id', 'token_expires_at',
            'is_token_expired', 'created_at', 'updated_at'
        ]
        # Note: refresh_token and access_token are intentionally not included in fields list
    
    def get_is_token_expired(self, obj):
        """Check if token is expired"""
        from django.utils import timezone
        return obj.token_expires_at < timezone.now()


class OutlookAuthUrlResponseSerializer(serializers.Serializer):
    """Response serializer for Outlook OAuth URL generation"""
    authorization_url = serializers.URLField(help_text="URL to redirect user for Microsoft OAuth")
    state = serializers.CharField(help_text="State parameter for CSRF protection")
    message = serializers.CharField(help_text="Instructions for frontend")


class OutlookOAuthCallbackSerializer(serializers.Serializer):
    """Response serializer for Outlook OAuth callback"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    calendar = OutlookCalendarSerializer(required=False)
    calendars = OutlookCalendarSerializer(many=True, required=False)
