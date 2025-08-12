import django_filters as filters
from core.models import LeadFunnel


class LeadFunnelFilter(filters.FilterSet):
    """Filter for LeadFunnel"""
    workspace = filters.UUIDFilter(field_name='workspace__id')
    is_active = filters.BooleanFilter(field_name='is_active')
    has_agent = filters.BooleanFilter(method='filter_has_agent')
    has_meta_form = filters.BooleanFilter(method='filter_has_meta_form')
    
    def filter_has_agent(self, queryset, name, value):
        """Filter funnels by whether they have an assigned agent"""
        if value is True:
            return queryset.filter(agent__isnull=False)
        elif value is False:
            return queryset.filter(agent__isnull=True)
        return queryset
    
    def filter_has_meta_form(self, queryset, name, value):
        """Filter funnels by whether they have a meta lead form"""
        if value is True:
            return queryset.filter(meta_lead_form__isnull=False)
        elif value is False:
            return queryset.filter(meta_lead_form__isnull=True)
        return queryset
    
    class Meta:
        model = LeadFunnel
        fields = ['workspace', 'is_active', 'has_agent', 'has_meta_form'] 