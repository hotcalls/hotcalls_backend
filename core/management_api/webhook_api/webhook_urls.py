from django.urls import path
from .views import WebhookInboundView

urlpatterns = [
    path('leads/<str:public_key>/', WebhookInboundView.as_view({'post': 'post'}), name='webhook-lead-inbound'),
]


