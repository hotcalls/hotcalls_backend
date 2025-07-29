import django_filters
from django_filters import rest_framework as filters
from core.models import MetaIntegration, MetaLeadForm


class MetaIntegrationFilter(filters.FilterSet):
    """Filter set for Meta Integration queries"""
    
    status = django_filters.ChoiceFilter(
        choices=[(choice[0], choice[1]) for choice in MetaIntegration._meta.get_field('status').choices],
        help_text="Filter by integration status"
    )
    workspace = django_filters.UUIDFilter(
        field_name='workspace__id',
        help_text="Filter by workspace ID"
    )
    business_account_id = django_filters.CharFilter(
        lookup_expr='icontains',
        help_text="Filter by business account ID"
    )
    page_id = django_filters.CharFilter(
        lookup_expr='icontains', 
        help_text="Filter by page ID"
    )
    created_after = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text="Filter integrations created after this date"
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text="Filter integrations created before this date"
    )
    
    class Meta:
        model = MetaIntegration
        fields = ['status', 'workspace', 'business_account_id', 'page_id']


class MetaLeadFormFilter(filters.FilterSet):
    """Filter set for Meta Lead Form queries"""
    
    meta_integration = django_filters.UUIDFilter(
        field_name='meta_integration__id',
        help_text="Filter by Meta integration ID"
    )
    workspace = django_filters.UUIDFilter(
        field_name='meta_integration__workspace__id',
        help_text="Filter by workspace ID"
    )
    meta_form_id = django_filters.CharFilter(
        lookup_expr='icontains',
        help_text="Filter by Meta form ID"
    )
    meta_lead_id = django_filters.CharFilter(
        lookup_expr='icontains',
        help_text="Filter by Meta lead ID"
    )
    has_lead = django_filters.BooleanFilter(
        field_name='lead',
        lookup_expr='isnull',
        exclude=True,
        help_text="Filter forms that have associated leads"
    )
    
    class Meta:
        model = MetaLeadForm
        fields = ['meta_integration', 'workspace', 'meta_form_id', 'meta_lead_id'] 