from django.urls import path
from .views import MetaWebhookView

urlpatterns = [
    # OAuth callback webhook (for Meta OAuth flow)
    path('oauth_hook/', MetaWebhookView.as_view({'post': 'oauth_hook'}), name='meta-oauth-hook'),
    
    # Lead webhook (Meta requires SAME URL for verification AND leads)
    path('lead_in/', MetaWebhookView.as_view({'get': 'verify_webhook', 'post': 'lead_in'}), name='meta-lead-webhook'),
] 