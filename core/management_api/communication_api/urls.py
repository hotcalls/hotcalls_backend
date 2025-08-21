from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import CommunicationViewSet

router = DefaultRouter()
router.register(r'', CommunicationViewSet, basename='communication')

urlpatterns = []
urlpatterns += router.urls


