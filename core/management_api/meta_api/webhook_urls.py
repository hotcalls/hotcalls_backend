from django.urls import path
from .views import MetaWebhookView

urlpatterns = [
    # OAuth callback webhook (for Meta OAuth flow)
    path('oauth_hook/', MetaWebhookView.as_view({'get': 'oauth_hook'}), name='meta-oauth-hook'),
    
    # Lead webhook (ONLY POST for actual leads)
    path('lead_in/', MetaWebhookView.as_view({'post': 'lead_in'}), name='meta-lead-webhook'),
    
    # Separate verification endpoint (ONLY GET for Meta verification)
    path('verify/', MetaWebhookView.as_view({'get': 'verify_webhook'}), name='meta-webhook-verify'),
] 