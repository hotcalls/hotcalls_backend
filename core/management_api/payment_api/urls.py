from django.urls import path
from .views import (
    get_workspace_stripe_info,
    create_stripe_customer,
    create_customer_portal_session,
    retrieve_stripe_customer,
    stripe_webhook,
    list_stripe_products,
    create_checkout_session,
    create_minute_pack_checkout,
    change_subscription_plan,
    get_subscription_status,
    cancel_subscription,
    resume_subscription,
    check_workspace_subscription,
    get_workspace_usage_status,
    purchase_minute_pack
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
    
    # Subscription management
    path('stripe/create-checkout-session/', 
         create_checkout_session, 
         name='create-checkout-session'),
    path('stripe/change-plan/', 
         change_subscription_plan, 
         name='change-subscription-plan'),

    # One-time minute pack checkout (Stripe Checkout)
    path('stripe/minute-pack-checkout/',
         create_minute_pack_checkout,
         name='minute-pack-checkout'),
    
    path('workspaces/<uuid:workspace_id>/subscription/', 
         get_subscription_status, 
         name='get-subscription-status'),
    
    path('workspaces/<uuid:workspace_id>/check-subscription/', 
         check_workspace_subscription, 
         name='check-workspace-subscription'),
    
    path('workspaces/<uuid:workspace_id>/subscription/cancel/', 
         cancel_subscription, 
         name='cancel-subscription'),
    path('workspaces/<uuid:workspace_id>/subscription/resume/', 
         resume_subscription, 
         name='resume-subscription'),
    
    # Usage and quota management
    path('workspaces/<uuid:workspace_id>/usage/', 
         get_workspace_usage_status, 
         name='workspace-usage-status'),
    
    # Minute pack purchase (100 minutes per pack at 0.19€/min)
    path('workspaces/<uuid:workspace_id>/purchase-minute-pack/',
         purchase_minute_pack,
         name='purchase-minute-pack'),
] 