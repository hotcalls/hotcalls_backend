import django_filters
from core.models import User, Blacklist
from django.db import models


class UserFilter(django_filters.FilterSet):
    """Filter for User model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    username = django_filters.CharFilter(lookup_expr='icontains')
    email = django_filters.CharFilter(lookup_expr='icontains')
    first_name = django_filters.CharFilter(lookup_expr='icontains')
    last_name = django_filters.CharFilter(lookup_expr='icontains')
    phone = django_filters.CharFilter(lookup_expr='icontains')
    
    # Choice filters
    status = django_filters.ChoiceFilter(choices=User._meta.get_field('status').choices)
    social_provider = django_filters.ChoiceFilter(choices=User._meta.get_field('social_provider').choices)
    
    # Boolean filters
    is_active = django_filters.BooleanFilter()
    
    # Date filters
    date_joined_after = django_filters.DateTimeFilter(field_name='date_joined', lookup_expr='gte')
    date_joined_before = django_filters.DateTimeFilter(field_name='date_joined', lookup_expr='lte')
    last_login_after = django_filters.DateTimeFilter(field_name='last_login', lookup_expr='gte')
    last_login_before = django_filters.DateTimeFilter(field_name='last_login', lookup_expr='lte')
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 'phone',
            'status', 'social_provider', 'is_active'
        ]
    
    def filter_search(self, queryset, name, value):
        """Global search across multiple fields"""
        return queryset.filter(
            models.Q(username__icontains=value) |
            models.Q(email__icontains=value) |
            models.Q(first_name__icontains=value) |
            models.Q(last_name__icontains=value) |
            models.Q(phone__icontains=value)
        )


class BlacklistFilter(django_filters.FilterSet):
    """Filter for Blacklist model"""
    
    # Text search filters
    search = django_filters.CharFilter(method='filter_search', label='Search')
    reason = django_filters.CharFilter(lookup_expr='icontains')
    
    # Choice filters
    status = django_filters.ChoiceFilter(choices=Blacklist._meta.get_field('status').choices)
    
    # User-related filters
    user__username = django_filters.CharFilter(lookup_expr='icontains')
    user__email = django_filters.CharFilter(lookup_expr='icontains')
    
    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')
    
    class Meta:
        model = Blacklist
        fields = ['reason', 'status', 'user__username', 'user__email']
    
    def filter_search(self, queryset, name, value):
        """Global search across multiple fields"""
        return queryset.filter(
            models.Q(reason__icontains=value) |
            models.Q(user__username__icontains=value) |
            models.Q(user__email__icontains=value)
        ) 