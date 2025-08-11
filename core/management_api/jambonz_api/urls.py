"""
Jambonz API URLs
"""

from django.urls import path
from . import views

urlpatterns = [
    path('auth/', views.JambonzAuthView.as_view(), name='jambonz-auth'),
    path('auth/legacy/', views.jambonz_auth_legacy, name='jambonz-auth-legacy'),
]
