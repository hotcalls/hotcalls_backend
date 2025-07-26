import django_filters
from django.db import models
from core.models import Calendar, CalendarConfiguration


class CalendarFilter(django_filters.FilterSet):
    """Filter for Calendar model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    account_id = django_filters.CharFilter(lookup_expr='icontains')
    
    # Choice filters
    calendar_type = django_filters.ChoiceFilter(choices=Calendar._meta.get_field('calendar_type').choices)
    
    # Workspace filters
    workspace__workspace_name = django_filters.CharFilter(lookup_expr='icontains')
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    # Configuration filters
    has_configurations = django_filters.BooleanFilter(method='filter_has_configurations')
    
    class Meta:
        model = Calendar
        fields = ['workspace', 'calendar_type', 'account_id']
    
    def filter_search(self, queryset, name, value):
        """Global search across multiple fields"""
        return queryset.filter(
            models.Q(account_id__icontains=value) |
            models.Q(workspace__workspace_name__icontains=value)
        )
    
    def filter_has_configurations(self, queryset, name, value):
        """Filter calendars with/without configurations"""
        if value:
            return queryset.filter(mapping_calendar_configurations__isnull=False).distinct()
        return queryset.filter(mapping_calendar_configurations__isnull=True)


class CalendarConfigurationFilter(django_filters.FilterSet):
    """Filter for CalendarConfiguration model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    sub_calendar_id = django_filters.CharFilter(lookup_expr='icontains')
    
    # Calendar filters
    calendar__calendar_type = django_filters.ChoiceFilter(choices=Calendar._meta.get_field('calendar_type').choices)
    calendar__workspace__workspace_name = django_filters.CharFilter(lookup_expr='icontains')
    calendar__account_id = django_filters.CharFilter(lookup_expr='icontains')
    
    # Duration filters
    duration_min = django_filters.NumberFilter(field_name='duration', lookup_expr='gte')
    duration_max = django_filters.NumberFilter(field_name='duration', lookup_expr='lte')
    prep_time_min = django_filters.NumberFilter(field_name='prep_time', lookup_expr='gte')
    prep_time_max = django_filters.NumberFilter(field_name='prep_time', lookup_expr='lte')
    
    # Time filters
    available_from = django_filters.TimeFilter(field_name='from_time', lookup_expr='gte')
    available_to = django_filters.TimeFilter(field_name='to_time', lookup_expr='lte')
    
    # Buffer filters
    days_buffer_min = django_filters.NumberFilter(field_name='days_buffer', lookup_expr='gte')
    days_buffer_max = django_filters.NumberFilter(field_name='days_buffer', lookup_expr='lte')
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    
    class Meta:
        model = CalendarConfiguration
        fields = [
            'calendar', 'duration', 'prep_time', 'days_buffer',
            'from_time', 'to_time'
        ]
    
    def filter_search(self, queryset, name, value):
        """Global search across multiple fields"""
        return queryset.filter(
            models.Q(sub_calendar_id__icontains=value) |
            models.Q(calendar__account_id__icontains=value) |
            models.Q(calendar__workspace__workspace_name__icontains=value)
        ) 