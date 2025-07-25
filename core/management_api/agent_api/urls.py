from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AgentViewSet, PhoneNumberViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'agents', AgentViewSet, basename='agent')
router.register(r'phone-numbers', PhoneNumberViewSet, basename='phonenumber')

urlpatterns = [
    path('', include(router.urls)),
] 