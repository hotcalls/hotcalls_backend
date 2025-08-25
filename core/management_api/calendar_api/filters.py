"""Filters for Calendar API"""
import django_filters
from core.models import Calendar


class CalendarFilter(django_filters.FilterSet):
    """Filter for Calendar model"""
    workspace = django_filters.UUIDFilter(field_name='workspace__id')
    provider = django_filters.ChoiceFilter(choices=[('google', 'Google'), ('outlook', 'Outlook')])
    active = django_filters.BooleanFilter()
    name = django_filters.CharFilter(lookup_expr='icontains')
    
    class Meta:
        model = Calendar
        fields = ['workspace', 'provider', 'active', 'name']