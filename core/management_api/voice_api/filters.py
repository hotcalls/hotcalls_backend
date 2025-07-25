import django_filters
from django.db import models
from core.models import Voice


class VoiceFilter(django_filters.FilterSet):
    """Filter for Voice model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    voice_external_id = django_filters.CharFilter(lookup_expr='icontains')
    provider = django_filters.CharFilter(lookup_expr='iexact')
    
    # Provider choices filter
    provider_exact = django_filters.ChoiceFilter(
        field_name='provider',
        choices=[
            ('openai', 'OpenAI'),
            ('elevenlabs', 'ElevenLabs'),
            ('google', 'Google'),
            ('azure', 'Azure'),
            ('aws', 'AWS'),
        ]
    )
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    created_date = django_filters.DateFilter(field_name='created_at', lookup_expr='date')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    # Agent relationship filters
    has_agents = django_filters.BooleanFilter(method='filter_has_agents')
    agent_count_min = django_filters.NumberFilter(method='filter_agent_count_min')
    agent_count_max = django_filters.NumberFilter(method='filter_agent_count_max')
    
    # Agent workspace filters  
    agent_workspace = django_filters.CharFilter(method='filter_agent_workspace')
    
    class Meta:
        model = Voice
        fields = ['provider', 'voice_external_id']
    
    def filter_search(self, queryset, name, value):
        """Global search across multiple fields"""
        return queryset.filter(
            models.Q(voice_external_id__icontains=value) |
            models.Q(provider__icontains=value)
        )
    
    def filter_has_agents(self, queryset, name, value):
        """Filter voices that have/don't have agents assigned"""
        if value:
            return queryset.filter(mapping_voice_agents__isnull=False).distinct()
        return queryset.filter(mapping_voice_agents__isnull=True).distinct()
    
    def filter_agent_count_min(self, queryset, name, value):
        """Filter voices with minimum number of agents"""
        return queryset.annotate(
            agent_count=models.Count('mapping_voice_agents')
        ).filter(agent_count__gte=value)
    
    def filter_agent_count_max(self, queryset, name, value):
        """Filter voices with maximum number of agents"""
        return queryset.annotate(
            agent_count=models.Count('mapping_voice_agents')
        ).filter(agent_count__lte=value)
    
    def filter_agent_workspace(self, queryset, name, value):
        """Filter voices used by agents in specific workspace"""
        return queryset.filter(
            mapping_voice_agents__workspace__workspace_name__icontains=value
        ).distinct() 