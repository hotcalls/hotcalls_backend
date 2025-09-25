from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WebhookViewSet, WebhookInboundView

router = DefaultRouter()
router.register(r'', WebhookViewSet, basename='webhook')

urlpatterns = [
    # Inbound webhook endpoint (for external systems to call)
    path('leads/<str:public_key>/', WebhookInboundView.as_view({'post': 'post'}), name='webhook-lead-inbound'),

    # Management API endpoints
    path('', include(router.urls)),
]


