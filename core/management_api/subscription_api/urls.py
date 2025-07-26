from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PlanViewSet, FeatureViewSet, PlanFeatureViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'plans', PlanViewSet, basename='plan')
router.register(r'features', FeatureViewSet, basename='feature')
router.register(r'plan-features', PlanFeatureViewSet, basename='planfeature')

urlpatterns = [
    path('', include(router.urls)),
] 