"""Serializers for Google Calendar API"""
from rest_framework import serializers
from core.models import GoogleCalendar, Calendar, GoogleSubAccount


class GoogleCalendarSerializer(serializers.ModelSerializer):
    """Serializer for GoogleCalendar model"""
    calendar_name = serializers.CharField(source='calendar.name', read_only=True)
    workspace_id = serializers.UUIDField(source='calendar.workspace.id', read_only=True)
    workspace_name = serializers.CharField(source='calendar.workspace.workspace_name', read_only=True)
    is_token_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = GoogleCalendar
        fields = [
            'id', 'calendar', 'calendar_name', 'workspace_id', 'workspace_name',
            'user', 'account_email', 'external_id', 'time_zone', 'access_role',
            'token_expires_at', 'is_token_expired', 'scopes', 'last_sync', 
            'sync_errors', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'token_expires_at', 'is_token_expired', 
            'created_at', 'updated_at'
        ]
        # Note: refresh_token and access_token are intentionally not included in fields list
    
    def get_is_token_expired(self, obj):
        """Check if token is expired"""
        from django.utils import timezone
        return obj.token_expires_at < timezone.now()


class GoogleAuthUrlResponseSerializer(serializers.Serializer):
    """Response serializer for Google OAuth URL generation"""
    authorization_url = serializers.URLField(help_text="URL to redirect user for Google OAuth")
    state = serializers.CharField(help_text="State parameter for CSRF protection")
    message = serializers.CharField(help_text="Instructions for frontend")


class GoogleOAuthCallbackSerializer(serializers.Serializer):
    """Response serializer for Google OAuth callback"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    calendar = GoogleCalendarSerializer(required=False)
    calendars = GoogleCalendarSerializer(many=True, required=False)


class GoogleSubAccountSerializer(serializers.ModelSerializer):
    """Serializer for GoogleSubAccount model"""
    main_account_email = serializers.CharField(source='google_calendar.account_email', read_only=True)
    calendar_id = serializers.UUIDField(source='google_calendar.calendar.id', read_only=True)
    calendar_name = serializers.CharField(source='google_calendar.calendar.name', read_only=True)
    workspace_id = serializers.UUIDField(source='google_calendar.calendar.workspace.id', read_only=True)
    
    class Meta:
        model = GoogleSubAccount
        fields = [
            'id', 'google_calendar', 'act_as_email', 'act_as_user_id', 'relationship',
            'active', 'main_account_email', 'calendar_id', 'calendar_name', 
            'workspace_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_act_as_email(self, value):
        """Validate email format"""
        if not value or '@' not in value:
            raise serializers.ValidationError("Invalid email format")
        return value.lower()
    
    def validate_relationship(self, value):
        """Validate relationship type"""
        valid_relationships = ['self', 'shared', 'delegate', 'domain_impersonation', 'resource']
        if value not in valid_relationships:
            raise serializers.ValidationError(f"Relationship must be one of: {', '.join(valid_relationships)}")
        return value
