from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LiveKitTokenViewSet

router = DefaultRouter()
router.register(r'tokens', LiveKitTokenViewSet, basename='livekit-tokens')

urlpatterns = [
    path('', include(router.urls)),
] 