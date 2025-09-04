from django.urls import path
from .views import MetaWebhookView

urlpatterns = [
    # Account validation endpoint (pre-flight check)
    path('validate_account/', MetaWebhookView.as_view({'get': 'validate_account', 'post': 'validate_account'}), name='meta-validate-account'),
    
    # OAuth callback webhook (for Meta OAuth flow) - Facebook sends GET requests
    path('oauth_hook/', MetaWebhookView.as_view({'get': 'oauth_hook', 'post': 'oauth_hook'}), name='meta-oauth-hook'),
    
    # Lead webhook (Meta requires SAME URL for verification AND leads)
    path('lead_in/', MetaWebhookView.as_view({'get': 'verify_webhook', 'post': 'lead_in'}), name='meta-lead-webhook'),
] 