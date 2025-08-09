import django_filters
from django.db import models
from core.models import CallLog, CallTask, CallStatus


class CallLogFilter(django_filters.FilterSet):
    """Filter for CallLog model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    from_number = django_filters.CharFilter(lookup_expr='icontains')
    to_number = django_filters.CharFilter(lookup_expr='icontains')
    disconnection_reason = django_filters.ChoiceFilter(choices=CallLog._meta.get_field('disconnection_reason').choices)
    
    # Choice filters
    direction = django_filters.ChoiceFilter(choices=CallLog._meta.get_field('direction').choices)
    status = django_filters.ChoiceFilter(choices=CallLog._meta.get_field('status').choices)
    
    # Agent filters
    agent = django_filters.UUIDFilter(field_name='agent__agent_id')
    agent__workspace = django_filters.UUIDFilter(field_name='agent__workspace__id')
    agent__workspace__workspace_name = django_filters.CharFilter(field_name='agent__workspace__workspace_name', lookup_expr='icontains')
    
    # Lead filters
    lead__name = django_filters.CharFilter(lookup_expr='icontains')
    lead__email = django_filters.CharFilter(lookup_expr='icontains')
    lead__phone = django_filters.CharFilter(lookup_expr='icontains')
    
    # Duration filters
    duration_min = django_filters.NumberFilter(field_name='duration', lookup_expr='gte')
    duration_max = django_filters.NumberFilter(field_name='duration', lookup_expr='lte')
    
    # Date filters
    timestamp_after = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='gte')
    timestamp_before = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='lte')
    date = django_filters.DateFilter(field_name='timestamp', lookup_expr='date')
    
    # Appointment datetime filters
    appointment_datetime_after = django_filters.DateTimeFilter(field_name='appointment_datetime', lookup_expr='gte')
    appointment_datetime_before = django_filters.DateTimeFilter(field_name='appointment_datetime', lookup_expr='lte')
    appointment_date = django_filters.DateFilter(field_name='appointment_datetime', lookup_expr='date')
    has_appointment = django_filters.BooleanFilter(method='filter_has_appointment')
    
    # Success/failure filters
    successful = django_filters.BooleanFilter(method='filter_successful')
    
    class Meta:
        model = CallLog
        fields = ['direction', 'status', 'lead', 'agent', 'from_number', 'to_number']
    
    def filter_search(self, queryset, name, value):
        """Global search across multiple fields"""
        return queryset.filter(
            models.Q(from_number__icontains=value) |
            models.Q(to_number__icontains=value) |
            models.Q(lead__name__icontains=value) |
            models.Q(lead__email__icontains=value) |
            models.Q(disconnection_reason__icontains=value) |
            models.Q(agent__workspace__workspace_name__icontains=value)
        )
    
    def filter_successful(self, queryset, name, value):
        """Filter successful/failed calls"""
        if value:
            # Successful calls (duration > 0 and no disconnection reason indicating failure)
            return queryset.filter(duration__gt=0)
        else:
            # Failed calls (duration = 0 or disconnection reason indicates failure)
            from core.models import DisconnectionReason
            failure_reasons = [
                DisconnectionReason.DIAL_BUSY,
                DisconnectionReason.DIAL_FAILED,
                DisconnectionReason.DIAL_NO_ANSWER,
                DisconnectionReason.INVALID_DESTINATION,
                DisconnectionReason.TELEPHONY_PROVIDER_PERMISSION_DENIED,
                DisconnectionReason.TELEPHONY_PROVIDER_UNAVAILABLE,
                DisconnectionReason.SIP_ROUTING_ERROR,
                DisconnectionReason.MARKED_AS_SPAM,
                DisconnectionReason.USER_DECLINED,
                DisconnectionReason.CONCURRENCY_LIMIT_REACHED,
                DisconnectionReason.NO_VALID_PAYMENT,
                DisconnectionReason.SCAM_DETECTED,
                DisconnectionReason.ERROR_LLM_WEBSOCKET_OPEN,
                DisconnectionReason.ERROR_LLM_WEBSOCKET_LOST_CONNECTION,
                DisconnectionReason.ERROR_LLM_WEBSOCKET_RUNTIME,
                DisconnectionReason.ERROR_LLM_WEBSOCKET_CORRUPT_PAYLOAD,
                DisconnectionReason.ERROR_NO_AUDIO_RECEIVED,
                DisconnectionReason.ERROR_ASR,
                DisconnectionReason.ERROR_RETELL,
                DisconnectionReason.ERROR_UNKNOWN,
                DisconnectionReason.ERROR_USER_NOT_JOINED,
                DisconnectionReason.REGISTERED_CALL_TIMEOUT,
            ]
            return queryset.filter(
                models.Q(duration=0) |
                models.Q(disconnection_reason__in=failure_reasons)
            )
    
    def filter_has_appointment(self, queryset, name, value):
        """Filter calls with/without appointments"""
        if value:
            # Calls with appointments scheduled
            return queryset.filter(appointment_datetime__isnull=False)
        else:
            # Calls without appointments
            return queryset.filter(appointment_datetime__isnull=True)


class CallTaskFilter(django_filters.FilterSet):
    """Filter for CallTask model"""
    
    # Status exact match
    status = django_filters.ChoiceFilter(
        field_name='status',
        choices=CallStatus.choices,
        help_text="Filter by exact status"
    )
    
    # Multiple status filter
    status__in = django_filters.MultipleChoiceFilter(
        field_name='status',
        choices=CallStatus.choices,
        help_text="Filter by multiple statuses"
    )
    
    # Phone number filter
    phone = django_filters.CharFilter(
        field_name='phone',
        lookup_expr='icontains',
        help_text="Filter by phone number (partial match)"
    )
    
    # Date range filters
    next_call__gte = django_filters.DateTimeFilter(
        field_name='next_call',
        lookup_expr='gte',
        help_text="Filter calls scheduled after this date/time"
    )
    next_call__lte = django_filters.DateTimeFilter(
        field_name='next_call',
        lookup_expr='lte',
        help_text="Filter calls scheduled before this date/time"
    )
    
    created_at__gte = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text="Filter tasks created after this date/time"
    )
    created_at__lte = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text="Filter tasks created before this date/time"
    )
    
    # Relationship filters
    agent = django_filters.UUIDFilter(
        field_name='agent__agent_id',
        help_text="Filter by agent ID"
    )
    workspace = django_filters.UUIDFilter(
        field_name='workspace__id',
        help_text="Filter by workspace ID"
    )
    lead = django_filters.UUIDFilter(
        field_name='lead__id',
        help_text="Filter by lead ID"
    )
    
    class Meta:
        model = CallTask
        fields = ['status', 'phone', 'agent', 'workspace', 'lead'] 