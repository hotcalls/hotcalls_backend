"""Serializers for Outlook Calendar API"""
from rest_framework import serializers
from core.models import OutlookCalendar, Calendar, OutlookSubAccount


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


class OutlookSubAccountSerializer(serializers.ModelSerializer):
    """Serializer for OutlookSubAccount model"""
    main_account_email = serializers.CharField(source='outlook_calendar.primary_email', read_only=True)
    calendar_id = serializers.UUIDField(source='outlook_calendar.calendar.id', read_only=True)
    calendar_name = serializers.CharField(source='outlook_calendar.calendar.name', read_only=True)
    workspace_id = serializers.UUIDField(source='outlook_calendar.calendar.workspace.id', read_only=True)
    
    class Meta:
        model = OutlookSubAccount
        fields = [
            'id', 'outlook_calendar', 'act_as_upn', 'mailbox_object_id', 'relationship',
            'active', 'main_account_email', 'calendar_id', 'calendar_name',
            'workspace_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_act_as_upn(self, value):
        """Validate UPN/email format"""
        if not value or '@' not in value:
            raise serializers.ValidationError("Invalid UPN/email format")
        return value.lower()
    
    def validate_relationship(self, value):
        """Validate relationship type"""
        valid_relationships = ['self', 'shared', 'delegate', 'app_only', 'resource']
        if value not in valid_relationships:
            raise serializers.ValidationError(f"Relationship must be one of: {', '.join(valid_relationships)}")
        return value
