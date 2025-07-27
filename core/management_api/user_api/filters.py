import django_filters
from django.contrib.auth import get_user_model
from core.models import Blacklist

User = get_user_model()


class UserFilter(django_filters.FilterSet):
    """Filters for User model with email-based authentication"""
    
    # Email-based filtering (replaces username)
    email = django_filters.CharFilter(lookup_expr='icontains', help_text="Filter by email address")
    email_verified = django_filters.BooleanFilter(field_name='is_email_verified', help_text="Filter by email verification status")
    
    # Name filtering
    first_name = django_filters.CharFilter(lookup_expr='icontains', help_text="Filter by first name")
    last_name = django_filters.CharFilter(lookup_expr='icontains', help_text="Filter by last name")
    full_name = django_filters.CharFilter(method='filter_full_name', help_text="Filter by full name (first + last)")
    
    # Contact filtering
    phone = django_filters.CharFilter(lookup_expr='icontains', help_text="Filter by phone number")
    
    # Status filtering
    status = django_filters.ChoiceFilter(choices=User._meta.get_field('status').choices, help_text="Filter by account status")
    is_active = django_filters.BooleanFilter(help_text="Filter by active status")
    is_staff = django_filters.BooleanFilter(help_text="Filter by staff status")
    
    # Social login filtering
    social_provider = django_filters.ChoiceFilter(
        choices=User._meta.get_field('social_provider').choices,
        help_text="Filter by social login provider"
    )
    has_social_login = django_filters.BooleanFilter(
        method='filter_has_social_login',
        help_text="Filter users with social login"
    )
    
    # Date filtering
    date_joined_after = django_filters.DateTimeFilter(
        field_name='date_joined',
        lookup_expr='gte',
        help_text="Filter users joined after this date"
    )
    date_joined_before = django_filters.DateTimeFilter(
        field_name='date_joined',
        lookup_expr='lte',
        help_text="Filter users joined before this date"
    )
    last_login_after = django_filters.DateTimeFilter(
        field_name='last_login',
        lookup_expr='gte',
        help_text="Filter users who logged in after this date"
    )
    last_login_before = django_filters.DateTimeFilter(
        field_name='last_login',
        lookup_expr='lte',
        help_text="Filter users who logged in before this date"
    )
    
    class Meta:
        model = User
        fields = {
            'email': ['exact', 'icontains'],
            'first_name': ['exact', 'icontains'],
            'last_name': ['exact', 'icontains'],
            'phone': ['exact', 'icontains'],
            'status': ['exact'],
            'is_active': ['exact'],
            'is_staff': ['exact'],
            'is_email_verified': ['exact'],
            'social_provider': ['exact'],
            'date_joined': ['exact', 'gte', 'lte'],
            'last_login': ['exact', 'gte', 'lte'],
        }
    
    def filter_full_name(self, queryset, name, value):
        """Filter by full name (combines first_name and last_name)"""
        if value:
            # Split the value to search both first and last name
            name_parts = value.split()
            if len(name_parts) == 1:
                # Single word - search in both first and last name
                return queryset.filter(
                    django_filters.Q(first_name__icontains=name_parts[0]) |
                    django_filters.Q(last_name__icontains=name_parts[0])
                )
            elif len(name_parts) >= 2:
                # Multiple words - assume first is first name, rest is last name
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
                return queryset.filter(
                    first_name__icontains=first_name,
                    last_name__icontains=last_name
                )
        return queryset
    
    def filter_has_social_login(self, queryset, name, value):
        """Filter users who have social login configured"""
        if value is True:
            return queryset.filter(social_id__isnull=False, social_provider__isnull=False)
        elif value is False:
            return queryset.filter(
                django_filters.Q(social_id__isnull=True) | django_filters.Q(social_provider__isnull=True)
            )
        return queryset


class BlacklistFilter(django_filters.FilterSet):
    """Filters for Blacklist model with email-based user references"""
    
    # User-related filtering (email-based)
    user_email = django_filters.CharFilter(
        field_name='user__email',
        lookup_expr='icontains',
        help_text="Filter by user's email address"
    )
    user_name = django_filters.CharFilter(
        method='filter_user_name',
        help_text="Filter by user's full name"
    )
    user_phone = django_filters.CharFilter(
        field_name='user__phone',
        lookup_expr='icontains',
        help_text="Filter by user's phone number"
    )
    
    # Blacklist-specific filtering
    reason = django_filters.CharFilter(lookup_expr='icontains', help_text="Filter by blacklist reason")
    status = django_filters.ChoiceFilter(
        choices=Blacklist._meta.get_field('status').choices,
        help_text="Filter by blacklist status"
    )
    
    # Date filtering
    created_after = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text="Filter blacklist entries created after this date"
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text="Filter blacklist entries created before this date"
    )
    updated_after = django_filters.DateTimeFilter(
        field_name='updated_at',
        lookup_expr='gte',
        help_text="Filter blacklist entries updated after this date"
    )
    updated_before = django_filters.DateTimeFilter(
        field_name='updated_at',
        lookup_expr='lte',
        help_text="Filter blacklist entries updated before this date"
    )
    
    class Meta:
        model = Blacklist
        fields = {
            'status': ['exact'],
            'reason': ['exact', 'icontains'],
            'created_at': ['exact', 'gte', 'lte'],
            'updated_at': ['exact', 'gte', 'lte'],
            'user__email': ['exact', 'icontains'],
            'user__first_name': ['exact', 'icontains'],
            'user__last_name': ['exact', 'icontains'],
            'user__phone': ['exact', 'icontains'],
        }
    
    def filter_user_name(self, queryset, name, value):
        """Filter by user's full name (combines first_name and last_name)"""
        if value:
            # Split the value to search both first and last name
            name_parts = value.split()
            if len(name_parts) == 1:
                # Single word - search in both first and last name
                return queryset.filter(
                    django_filters.Q(user__first_name__icontains=name_parts[0]) |
                    django_filters.Q(user__last_name__icontains=name_parts[0])
                )
            elif len(name_parts) >= 2:
                # Multiple words - assume first is first name, rest is last name
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
                return queryset.filter(
                    user__first_name__icontains=first_name,
                    user__last_name__icontains=last_name
                )
        return queryset 