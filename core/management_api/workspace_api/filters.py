import django_filters
from django.db import models
from core.models import Workspace


class WorkspaceFilter(django_filters.FilterSet):
    """Filter for Workspace model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    workspace_name = django_filters.CharFilter(lookup_expr='icontains')
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    # User-related filters
    has_user = django_filters.CharFilter(method='filter_has_user', label='Has User')
    user_count_min = django_filters.NumberFilter(method='filter_user_count_min')
    user_count_max = django_filters.NumberFilter(method='filter_user_count_max')
    empty_workspace = django_filters.BooleanFilter(method='filter_empty_workspace')
    
    class Meta:
        model = Workspace
        fields = ['workspace_name']
    
    def filter_search(self, queryset, name, value):
        """Global search across workspace name"""
        return queryset.filter(workspace_name__icontains=value)
    
    def filter_has_user(self, queryset, name, value):
        """Filter workspaces that have a specific user"""
        return queryset.filter(
            models.Q(mapping_user_workspaces__email__icontains=value) |
            models.Q(mapping_user_workspaces__first_name__icontains=value) |
            models.Q(mapping_user_workspaces__last_name__icontains=value)
        ).distinct()
    
    def filter_user_count_min(self, queryset, name, value):
        """Filter workspaces with minimum number of users"""
        return queryset.annotate(
            user_count=models.Count('mapping_user_workspaces')
        ).filter(user_count__gte=value)
    
    def filter_user_count_max(self, queryset, name, value):
        """Filter workspaces with maximum number of users"""
        return queryset.annotate(
            user_count=models.Count('mapping_user_workspaces')
        ).filter(user_count__lte=value)
    
    def filter_empty_workspace(self, queryset, name, value):
        """Filter empty workspaces (no users)"""
        if value:
            return queryset.annotate(
                user_count=models.Count('mapping_user_workspaces')
            ).filter(user_count=0)
        return queryset 