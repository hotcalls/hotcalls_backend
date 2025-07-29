from django.urls import path
from .views import (
    get_workspace_stripe_info,
    create_stripe_customer,
    create_customer_portal_session,
    retrieve_stripe_customer,
    stripe_webhook,
    list_stripe_products
)

urlpatterns = [
    # Stripe customer management
    path('workspaces/<uuid:workspace_id>/stripe-info/', 
         get_workspace_stripe_info, 
         name='workspace-stripe-info'),
    
    path('stripe/create-customer/', 
         create_stripe_customer, 
         name='create-stripe-customer'),
    
    path('stripe/portal-session/', 
         create_customer_portal_session, 
         name='create-portal-session'),
    
    path('stripe/customer-details/', 
         retrieve_stripe_customer, 
         name='retrieve-stripe-customer'),
    
    # Stripe webhook
    path('stripe/webhook/', 
         stripe_webhook, 
         name='stripe-webhook'),

    # Stripe products
    path('stripe/products/', 
         list_stripe_products, 
         name='list-stripe-products'),
] 