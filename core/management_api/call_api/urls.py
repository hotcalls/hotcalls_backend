from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CallLogViewSet, CallTaskViewSet, make_test_call, end_of_call

# Create router and register viewsets
router = DefaultRouter()
router.register(r'call-logs', CallLogViewSet, basename='calllog')
router.register(r'call-tasks', CallTaskViewSet, basename='calltask')

urlpatterns = [
    path('', include(router.urls)),
    # Direct test call endpoint for easier frontend access
    path('make_test_call/', make_test_call, name='make_test_call'),
    # End-of-call signal from agent/backend
    path('end-of-call/', end_of_call, name='end_of_call'),
] 