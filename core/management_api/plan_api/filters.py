import django_filters
from django.db.models import Q
from core.models import Plan, Feature, PlanFeature


class PlanFilter(django_filters.FilterSet):
    """Filter für Plan API"""
    
    # Preis-Filterung
    price_min = django_filters.NumberFilter(field_name='price_monthly', lookup_expr='gte')
    price_max = django_filters.NumberFilter(field_name='price_monthly', lookup_expr='lte')
    
    # Plan-Name (case insensitive)
    name = django_filters.CharFilter(field_name='plan_name', lookup_expr='icontains')
    
    # Nur aktive Pläne
    active = django_filters.BooleanFilter(field_name='is_active')
    
    # Feature-basierte Filter
    has_feature = django_filters.CharFilter(method='filter_has_feature')
    min_minutes = django_filters.NumberFilter(method='filter_min_minutes')
    max_users = django_filters.NumberFilter(method='filter_max_users')
    
    # Spezielle Plan-Typen
    enterprise_only = django_filters.BooleanFilter(method='filter_enterprise')
    affordable_plans = django_filters.BooleanFilter(method='filter_affordable')
    
    class Meta:
        model = Plan
        fields = ['is_active', 'price_monthly']
    
    def filter_has_feature(self, queryset, name, value):
        """Filtere Pläne mit bestimmtem Feature"""
        return queryset.filter(
            planfeature__feature__feature_name__icontains=value
        ).distinct()
    
    def filter_min_minutes(self, queryset, name, value):
        """Filtere Pläne mit mindestens X Minuten"""
        return queryset.filter(
            planfeature__feature__feature_name='call_minutes',
            planfeature__limit__gte=value
        ).distinct()
    
    def filter_max_users(self, queryset, name, value):
        """Filtere Pläne mit maximal X Benutzern"""
        return queryset.filter(
            Q(planfeature__feature__feature_name='max_users', planfeature__limit__lte=value) |
            Q(planfeature__feature__feature_name='max_users', planfeature__limit=999999)  # Unlimited
        ).distinct()
    
    def filter_enterprise(self, queryset, name, value):
        """Filtere nur Enterprise-Pläne (ohne monatlichen Preis)"""
        if value:
            return queryset.filter(price_monthly__isnull=True)
        return queryset.filter(price_monthly__isnull=False)
    
    def filter_affordable(self, queryset, name, value):
        """Filtere erschwingliche Pläne (unter 400€)"""
        if value:
            return queryset.filter(
                price_monthly__lt=400,
                price_monthly__isnull=False
            )
        return queryset


class FeatureFilter(django_filters.FilterSet):
    """Filter für Features"""
    
    name = django_filters.CharFilter(field_name='feature_name', lookup_expr='icontains')
    description = django_filters.CharFilter(field_name='description', lookup_expr='icontains')
    
    class Meta:
        model = Feature
        fields = ['feature_name']


class PlanFeatureFilter(django_filters.FilterSet):
    """Filter für Plan-Feature Zuordnungen"""
    
    plan_name = django_filters.CharFilter(field_name='plan__plan_name', lookup_expr='icontains')
    feature_name = django_filters.CharFilter(field_name='feature__feature_name', lookup_expr='icontains')
    
    # Limit-basierte Filter
    limit_min = django_filters.NumberFilter(field_name='limit', lookup_expr='gte')
    limit_max = django_filters.NumberFilter(field_name='limit', lookup_expr='lte')
    unlimited = django_filters.BooleanFilter(method='filter_unlimited')
    
    class Meta:
        model = PlanFeature
        fields = ['plan', 'feature', 'limit']
    
    def filter_unlimited(self, queryset, name, value):
        """Filtere unlimited Features (999999)"""
        if value:
            return queryset.filter(limit=999999)
        return queryset.exclude(limit=999999) 