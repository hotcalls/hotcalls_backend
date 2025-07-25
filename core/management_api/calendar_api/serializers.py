from rest_framework import serializers
from core.models import Calendar, CalendarConfiguration, Workspace


class CalendarSerializer(serializers.ModelSerializer):
    """Serializer for Calendar model"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    config_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Calendar
        fields = [
            'id', 'workspace', 'workspace_name', 'calendar_type', 
            'account_id', 'auth_token', 'config_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'auth_token': {'write_only': True}  # Don't expose auth tokens in responses
        }
    
    def get_config_count(self, obj):
        """Get the number of configurations for this calendar"""
        return obj.mapping_calendar_configurations.count()


class CalendarCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating calendars"""
    
    class Meta:
        model = Calendar
        fields = ['workspace', 'calendar_type', 'account_id', 'auth_token']


class CalendarConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for CalendarConfiguration model"""
    calendar_workspace_name = serializers.CharField(source='calendar.workspace.workspace_name', read_only=True)
    calendar_type = serializers.CharField(source='calendar.calendar_type', read_only=True)
    calendar_account_id = serializers.CharField(source='calendar.account_id', read_only=True)
    
    class Meta:
        model = CalendarConfiguration
        fields = [
            'id', 'calendar', 'calendar_workspace_name', 'calendar_type', 
            'calendar_account_id', 'sub_calendar_id', 'duration', 'prep_time',
            'days_buffer', 'from_time', 'to_time', 'workdays', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CalendarConfigurationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating calendar configurations"""
    
    class Meta:
        model = CalendarConfiguration
        fields = [
            'calendar', 'sub_calendar_id', 'duration', 'prep_time',
            'days_buffer', 'from_time', 'to_time', 'workdays'
        ]


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