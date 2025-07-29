from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MetaIntegrationViewSet, MetaLeadFormViewSet

# Create router and register viewsets for CRUD management
router = DefaultRouter()
router.register(r'integrations', MetaIntegrationViewSet, basename='meta-integration')
router.register(r'lead-forms', MetaLeadFormViewSet, basename='meta-leadform')

urlpatterns = [
    path('', include(router.urls)),
] 