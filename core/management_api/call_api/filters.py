import django_filters
from django.db import models
from core.models import CallLog


class CallLogFilter(django_filters.FilterSet):
    """Filter for CallLog model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    from_number = django_filters.CharFilter(lookup_expr='icontains')
    to_number = django_filters.CharFilter(lookup_expr='icontains')
    disconnection_reason = django_filters.CharFilter(lookup_expr='icontains')
    
    # Choice filters
    direction = django_filters.ChoiceFilter(choices=CallLog._meta.get_field('direction').choices)
    
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
    
    # Success/failure filters
    successful = django_filters.BooleanFilter(method='filter_successful')
    
    class Meta:
        model = CallLog
        fields = ['direction', 'lead', 'from_number', 'to_number']
    
    def filter_search(self, queryset, name, value):
        """Global search across multiple fields"""
        return queryset.filter(
            models.Q(from_number__icontains=value) |
            models.Q(to_number__icontains=value) |
            models.Q(lead__name__icontains=value) |
            models.Q(lead__email__icontains=value) |
            models.Q(disconnection_reason__icontains=value)
        )
    
    def filter_successful(self, queryset, name, value):
        """Filter successful/failed calls"""
        if value:
            # Successful calls (duration > 0 and no disconnection reason indicating failure)
            return queryset.filter(duration__gt=0)
        else:
            # Failed calls (duration = 0 or disconnection reason indicates failure)
            return queryset.filter(
                models.Q(duration=0) |
                models.Q(disconnection_reason__icontains='busy') |
                models.Q(disconnection_reason__icontains='failed') |
                models.Q(disconnection_reason__icontains='no answer')
            ) 