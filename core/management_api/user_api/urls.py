from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, BlacklistViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'blacklist', BlacklistViewSet, basename='blacklist')

urlpatterns = [
    path('', include(router.urls)),
] 