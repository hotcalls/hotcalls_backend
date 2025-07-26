from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VoiceViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'voices', VoiceViewSet, basename='voice')

urlpatterns = [
    path('', include(router.urls)),
] 