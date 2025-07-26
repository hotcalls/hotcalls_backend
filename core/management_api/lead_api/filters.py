import django_filters
from django.db import models
from core.models import Lead


class LeadFilter(django_filters.FilterSet):
    """Filter for Lead model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    name = django_filters.CharFilter(lookup_expr='icontains')
    surname = django_filters.CharFilter(lookup_expr='icontains')
    email = django_filters.CharFilter(lookup_expr='icontains')
    phone = django_filters.CharFilter(lookup_expr='icontains')
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    # Metadata filters
    has_metadata = django_filters.BooleanFilter(method='filter_has_metadata')
    metadata_key = django_filters.CharFilter(method='filter_metadata_key')
    metadata_value = django_filters.CharFilter(method='filter_metadata_value')
    
    class Meta:
        model = Lead
        fields = ['name', 'surname', 'email', 'phone']
    
    def filter_search(self, queryset, name, value):
        """Global search across multiple fields"""
        return queryset.filter(
            models.Q(name__icontains=value) |
            models.Q(surname__icontains=value) |
            models.Q(email__icontains=value) |
            models.Q(phone__icontains=value)
        )
    
    def filter_has_metadata(self, queryset, name, value):
        """Filter leads with or without metadata"""
        if value:
            return queryset.exclude(meta_data={})
        return queryset.filter(meta_data={})
    
    def filter_metadata_key(self, queryset, name, value):
        """Filter leads that have a specific key in metadata"""
        return queryset.filter(meta_data__has_key=value)
    
    def filter_metadata_value(self, queryset, name, value):
        """Filter leads that have a specific value in metadata"""
        return queryset.filter(meta_data__icontains=value) 