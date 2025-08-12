from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LeadFunnelViewSet, LeadProcessingStatsViewSet

router = DefaultRouter()
router.register(r'lead-funnels', LeadFunnelViewSet, basename='leadfunnel')
router.register(r'lead-stats', LeadProcessingStatsViewSet, basename='leadstats')

urlpatterns = [
    path('', include(router.urls)),
] 