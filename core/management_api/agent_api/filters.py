import django_filters
from django.db import models
from core.models import Agent, PhoneNumber


class AgentFilter(django_filters.FilterSet):
    """Filter for Agent model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    
    # NEW: Name and status filters
    name = django_filters.CharFilter(lookup_expr='icontains')
    status = django_filters.ChoiceFilter(choices=[('active', 'Active'), ('paused', 'Paused')])
    
    # NEW: Greeting filters  
    greeting_inbound = django_filters.CharFilter(lookup_expr='icontains')
    greeting_outbound = django_filters.CharFilter(lookup_expr='icontains')
    
    # UPDATED: Voice filters (now FK to Voice model)
    voice = django_filters.UUIDFilter(field_name='voice__id')
    voice_provider = django_filters.CharFilter(field_name='voice__provider', lookup_expr='iexact')
    voice_external_id = django_filters.CharFilter(field_name='voice__voice_external_id', lookup_expr='icontains')
    has_voice = django_filters.BooleanFilter(method='filter_has_voice')
    
    # EXISTING: Other filters
    language = django_filters.CharFilter(lookup_expr='icontains')
    character = django_filters.CharFilter(lookup_expr='icontains')
    prompt = django_filters.CharFilter(lookup_expr='icontains')
    config_id = django_filters.CharFilter(lookup_expr='icontains')
    
    # Workspace filters
    workspace__workspace_name = django_filters.CharFilter(lookup_expr='icontains')
    
    # Number filters
    retry_interval_min = django_filters.NumberFilter(field_name='retry_interval', lookup_expr='gte')
    retry_interval_max = django_filters.NumberFilter(field_name='retry_interval', lookup_expr='lte')
    
    # Time filters
    call_from_after = django_filters.TimeFilter(field_name='call_from', lookup_expr='gte')
    call_from_before = django_filters.TimeFilter(field_name='call_from', lookup_expr='lte')
    call_to_after = django_filters.TimeFilter(field_name='call_to', lookup_expr='gte')
    call_to_before = django_filters.TimeFilter(field_name='call_to', lookup_expr='lte')
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    # Phone number filters
    has_phone_number = django_filters.CharFilter(method='filter_has_phone_number')
    phone_count_min = django_filters.NumberFilter(method='filter_phone_count_min')
    phone_count_max = django_filters.NumberFilter(method='filter_phone_count_max')
    
    # Calendar filters
    has_calendar_config = django_filters.BooleanFilter(method='filter_has_calendar_config')
    
    class Meta:
        model = Agent
        fields = ['workspace', 'name', 'status', 'voice', 'language', 'retry_interval', 'character', 'prompt']
    
    def filter_search(self, queryset, name, value):
        """Global search across multiple fields"""
        return queryset.filter(
            models.Q(name__icontains=value) |
            models.Q(language__icontains=value) |
            models.Q(character__icontains=value) |
            models.Q(prompt__icontains=value) |
            models.Q(greeting_inbound__icontains=value) |
            models.Q(greeting_outbound__icontains=value) |
            models.Q(workspace__workspace_name__icontains=value) |
            models.Q(voice__provider__icontains=value) |
            models.Q(voice__voice_external_id__icontains=value)
        )
    
    def filter_has_voice(self, queryset, name, value):
        """Filter agents that have/don't have a voice assigned"""
        if value:
            return queryset.filter(voice__isnull=False)
        return queryset.filter(voice__isnull=True)
    
    def filter_has_phone_number(self, queryset, name, value):
        """Filter agents that have a specific phone number"""
        return queryset.filter(mapping_agent_phonenumbers__phonenumber__icontains=value).distinct()
    
    def filter_phone_count_min(self, queryset, name, value):
        """Filter agents with minimum number of phone numbers"""
        return queryset.annotate(
            phone_count=models.Count('mapping_agent_phonenumbers')
        ).filter(phone_count__gte=value)
    
    def filter_phone_count_max(self, queryset, name, value):
        """Filter agents with maximum number of phone numbers"""
        return queryset.annotate(
            phone_count=models.Count('mapping_agent_phonenumbers')
        ).filter(phone_count__lte=value)
    
    def filter_has_calendar_config(self, queryset, name, value):
        """Filter agents with/without calendar configuration"""
        if value:
            return queryset.filter(calendar_configuration__isnull=False)
        return queryset.filter(calendar_configuration__isnull=True)


class PhoneNumberFilter(django_filters.FilterSet):
    """Filter for PhoneNumber model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    phonenumber = django_filters.CharFilter(lookup_expr='icontains')
    
    # Boolean filters
    is_active = django_filters.BooleanFilter()
    unassigned = django_filters.BooleanFilter(method='filter_unassigned')
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    
    # Agent filters
    assigned_to_agent = django_filters.CharFilter(method='filter_assigned_to_agent')
    
    class Meta:
        model = PhoneNumber
        fields = ['phonenumber', 'is_active']
    
    def filter_search(self, queryset, name, value):
        """Global search across phone number"""
        return queryset.filter(phonenumber__icontains=value)
    
    def filter_unassigned(self, queryset, name, value):
        """Filter phone numbers not assigned to any agent"""
        if value:
            return queryset.filter(mapping_agent_phonenumbers__isnull=True)
        return queryset
    
    def filter_assigned_to_agent(self, queryset, name, value):
        """Filter phone numbers assigned to a specific agent"""
        return queryset.filter(
            mapping_agent_phonenumbers__workspace__workspace_name__icontains=value
        ).distinct() 