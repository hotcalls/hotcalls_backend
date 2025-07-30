import django_filters
from django.db import models
from core.models import Plan, Feature, PlanFeature, EndpointFeature, FeatureUnit, HTTPMethod


class PlanFilter(django_filters.FilterSet):
    """Filter for Plan model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    plan_name = django_filters.CharFilter(lookup_expr='icontains')
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    # Feature-related filters
    has_feature = django_filters.CharFilter(method='filter_has_feature', label='Has Feature')
    feature_count_min = django_filters.NumberFilter(method='filter_feature_count_min')
    feature_count_max = django_filters.NumberFilter(method='filter_feature_count_max')
    
    class Meta:
        model = Plan
        fields = ['plan_name']
    
    def filter_search(self, queryset, name, value):
        """Global search across plan name"""
        return queryset.filter(plan_name__icontains=value)
    
    def filter_has_feature(self, queryset, name, value):
        """Filter plans that have a specific feature"""
        return queryset.filter(features__feature_name__icontains=value).distinct()
    
    def filter_feature_count_min(self, queryset, name, value):
        """Filter plans with minimum number of features"""
        return queryset.annotate(
            feature_count=models.Count('features')
        ).filter(feature_count__gte=value)
    
    def filter_feature_count_max(self, queryset, name, value):
        """Filter plans with maximum number of features"""
        return queryset.annotate(
            feature_count=models.Count('features')
        ).filter(feature_count__lte=value)


class FeatureFilter(django_filters.FilterSet):
    """Filter for Feature model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    feature_name = django_filters.CharFilter(lookup_expr='icontains')
    description = django_filters.CharFilter(lookup_expr='icontains')
    unit = django_filters.ChoiceFilter(choices=FeatureUnit.choices)
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    # Plan-related filters
    assigned_to_plan = django_filters.CharFilter(method='filter_assigned_to_plan')
    unassigned = django_filters.BooleanFilter(method='filter_unassigned')
    
    class Meta:
        model = Feature
        fields = ['feature_name', 'description', 'unit']
    
    def filter_search(self, queryset, name, value):
        """Global search across feature name and description"""
        return queryset.filter(
            models.Q(feature_name__icontains=value) |
            models.Q(description__icontains=value)
        )
    
    def filter_assigned_to_plan(self, queryset, name, value):
        """Filter features assigned to a specific plan"""
        return queryset.filter(mapping_plan_features__plan_name__icontains=value).distinct()
    
    def filter_unassigned(self, queryset, name, value):
        """Filter features not assigned to any plan"""
        if value:
            return queryset.filter(mapping_plan_features__isnull=True)
        return queryset


class EndpointFeatureFilter(django_filters.FilterSet):
    """Filter for EndpointFeature model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    feature_name = django_filters.CharFilter(field_name='feature__feature_name', lookup_expr='icontains')
    route_name = django_filters.CharFilter(lookup_expr='icontains')
    http_method = django_filters.ChoiceFilter(choices=HTTPMethod.choices)
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    class Meta:
        model = EndpointFeature
        fields = ['feature', 'route_name', 'http_method']
    
    def filter_search(self, queryset, name, value):
        """Global search across route name and feature name"""
        return queryset.filter(
            models.Q(route_name__icontains=value) |
            models.Q(feature__feature_name__icontains=value)
        )


class PlanFeatureFilter(django_filters.FilterSet):
    """Filter for PlanFeature model"""
    
    # Plan-related filters
    plan__plan_name = django_filters.CharFilter(lookup_expr='icontains')
    
    # Feature-related filters
    feature__feature_name = django_filters.CharFilter(lookup_expr='icontains')
    feature__description = django_filters.CharFilter(lookup_expr='icontains')
    
    # Limit filters
    limit_min = django_filters.NumberFilter(field_name='limit', lookup_expr='gte')
    limit_max = django_filters.NumberFilter(field_name='limit', lookup_expr='lte')
    limit_exact = django_filters.NumberFilter(field_name='limit')
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    class Meta:
        model = PlanFeature
        fields = [
            'plan', 'feature', 'limit',
            'plan__plan_name', 'feature__feature_name'
        ] 