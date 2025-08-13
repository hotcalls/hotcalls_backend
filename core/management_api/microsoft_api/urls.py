from django.urls import path
from .views import MicrosoftWebhookView

urlpatterns = [
    path('webhook/', MicrosoftWebhookView.as_view({'get': 'verify', 'post': 'notify'}), name='microsoft-webhook'),
]


