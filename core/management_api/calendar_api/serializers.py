from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Calendar, CalendarConfiguration, GoogleCalendarConnection, GoogleCalendar, Workspace


class GoogleCalendarDetailSerializer(serializers.ModelSerializer):
    """Google-specific calendar details"""
    # Note: GoogleCalendar model doesn't have connection field anymore
    # Connection info is handled separately through GoogleCalendarConnection
    
    class Meta:
        model = GoogleCalendar
        fields = [
            'external_id', 'primary', 'time_zone', 'created_at', 'updated_at'
        ]


class CalendarSerializer(serializers.ModelSerializer):
    """Serializer for Calendar model with provider details"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    config_count = serializers.SerializerMethodField()
    provider_details = serializers.SerializerMethodField()
    connection_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Calendar
        fields = [
            'id', 'workspace', 'workspace_name', 'name', 'provider', 
            'active', 'config_count', 'provider_details', 'connection_status',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.IntegerField)
    def get_config_count(self, obj) -> int:
        """Get the number of configurations for this calendar"""
        return obj.configurations.count()
    
    @extend_schema_field(serializers.DictField)
    def get_provider_details(self, obj):
        """Get provider-specific details"""
        if obj.provider == 'google' and hasattr(obj, 'google_calendar'):
            return GoogleCalendarDetailSerializer(obj.google_calendar).data
        return None
    
    @extend_schema_field(serializers.CharField)
    def get_connection_status(self, obj):
        """Get connection status"""
        if obj.provider == 'google' and hasattr(obj, 'google_calendar'):
            # Find the connection through workspace since GoogleCalendar doesn't have connection field
            try:
                connections = GoogleCalendarConnection.objects.filter(
                    workspace=obj.workspace,
                    active=True
                )
                if connections.exists():
                    connection = connections.first()
                    if not connection.active:
                        return 'disconnected'
                    elif connection.sync_errors:
                        return 'error'
                    else:
                        return 'connected'
                else:
                    return 'disconnected'
            except Exception:
                return 'unknown'
        return 'unknown'


class GoogleCalendarConnectionSerializer(serializers.ModelSerializer):
    """Google Calendar Connection management"""
    calendar_count = serializers.SerializerMethodField()
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    status = serializers.SerializerMethodField()
    
    class Meta:
        model = GoogleCalendarConnection
        fields = [
            'id', 'workspace', 'workspace_name', 'account_email', 'active', 
            'last_sync', 'calendar_count', 'status', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'last_sync']
        extra_kwargs = {
            'refresh_token': {'write_only': True},
            'access_token': {'write_only': True}
        }
    
    @extend_schema_field(serializers.IntegerField)
    def get_calendar_count(self, obj) -> int:
        """Get number of calendars for this connection"""
        # Count calendars in the workspace since there's no direct connection->calendars relationship
        return Calendar.objects.filter(workspace=obj.workspace, provider='google', active=True).count()
    
    @extend_schema_field(serializers.CharField)
    def get_status(self, obj):
        """Get connection status"""
        if not obj.active:
            return 'disconnected'
        elif obj.sync_errors:
            return 'error'
        else:
            return 'connected'


class CalendarConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for CalendarConfiguration model"""
    calendar_workspace_name = serializers.CharField(source='calendar.workspace.workspace_name', read_only=True)
    calendar_name = serializers.CharField(source='calendar.name', read_only=True)
    calendar_provider = serializers.CharField(source='calendar.provider', read_only=True)
    
    # Support both field names for backward compatibility
    conflict_calendars = serializers.JSONField(source='conflict_check_calendars', required=False)
    
    class Meta:
        model = CalendarConfiguration
        fields = [
            'id', 'calendar', 'calendar_workspace_name', 'calendar_name', 
            'calendar_provider', 'name', 'meeting_type', 'meeting_link', 'meeting_address',
            'duration', 'prep_time', 'days_buffer', 'from_time', 'to_time', 'workdays', 
            'conflict_check_calendars', 'conflict_calendars', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CalendarConfigurationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating calendar configurations"""
    
    # Support both field names for backward compatibility
    conflict_calendars = serializers.JSONField(source='conflict_check_calendars', required=False)
    
    class Meta:
        model = CalendarConfiguration
        fields = [
            'calendar', 'name', 'meeting_type', 'meeting_link', 'meeting_address',
            'duration', 'prep_time', 'days_buffer', 'from_time', 'to_time', 'workdays', 
            'conflict_check_calendars', 'conflict_calendars'
        ]
    
    def validate_workdays(self, value):
        """Validate workdays format"""
        valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        if not isinstance(value, list):
            raise serializers.ValidationError("Workdays must be a list")
        
        for day in value:
            if day.lower() not in valid_days:
                raise serializers.ValidationError(f"Invalid workday: {day}")
        
        return value
    
    def validate_conflict_check_calendars(self, value):
        """Validate conflict_check_calendars format"""
        if not isinstance(value, list):
            raise serializers.ValidationError("conflict_check_calendars must be a list")
        
        # Optional: Validate that calendar IDs exist (can be added later if needed)
        # for calendar_id in value:
        #     if not Calendar.objects.filter(id=calendar_id).exists():
        #         raise serializers.ValidationError(f"Calendar with ID {calendar_id} does not exist")
        
        return value
    
    def validate_conflict_calendars(self, value):
        """Validate conflict_calendars format (alias for conflict_check_calendars)"""
        return self.validate_conflict_check_calendars(value)


class CalendarAvailabilityRequestSerializer(serializers.Serializer):
    """Serializer for checking calendar availability"""
    date = serializers.DateField(help_text="Date to check availability for")
    duration_minutes = serializers.IntegerField(min_value=1, help_text="Duration in minutes")


class CalendarAvailabilityResponseSerializer(serializers.Serializer):
    """Serializer for calendar availability response"""
    date = serializers.DateField()
    available_slots = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of available time slots"
    )
    calendar_config_id = serializers.UUIDField()
    busy_times = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of busy time periods from Google Calendar"
    )


class GoogleOAuthCallbackSerializer(serializers.Serializer):
    """Serializer for Google OAuth callback response"""
    success = serializers.BooleanField()
    connection = serializers.DictField()
    calendars = CalendarSerializer(many=True)
    message = serializers.CharField()


class EventCreateSerializer(serializers.Serializer):
    """Serializer for creating calendar events"""
    calendar_id = serializers.CharField(help_text="External calendar ID (Google Calendar ID)")
    summary = serializers.CharField(max_length=500, help_text="Event title")
    description = serializers.CharField(required=False, allow_blank=True, help_text="Event description")
    start_time = serializers.DateTimeField(help_text="Event start time")
    end_time = serializers.DateTimeField(help_text="Event end time")
    attendee_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        help_text="List of attendee email addresses"
    )
    
    def validate(self, data):
        """Validate event data"""
        if data['end_time'] <= data['start_time']:
            raise serializers.ValidationError("End time must be after start time")
        
        return data 