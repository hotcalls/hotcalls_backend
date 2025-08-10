from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LeadFunnelViewSet

router = DefaultRouter()
router.register(r'lead-funnels', LeadFunnelViewSet, basename='leadfunnel')

urlpatterns = [
    path('', include(router.urls)),
] 