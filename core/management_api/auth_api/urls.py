from django.urls import path
from . import views

app_name = 'auth_api'

urlpatterns = [
    # User registration and authentication
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Email verification
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('resend-verification/', views.resend_verification, name='resend_verification'),
    
    # User profile
    path('profile/', views.profile, name='profile'),
    
    # Password reset
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('reset-password/<str:token>/', views.password_reset_confirm, name='password_reset_confirm'),
] 