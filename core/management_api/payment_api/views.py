import stripe
from django.db import transaction
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.response import Response
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework.permissions import IsAuthenticated, AllowAny

from core.models import Workspace, User
from .serializers import (
    StripeCustomerSerializer,
    CreateStripeCustomerSerializer,
    StripePortalSessionSerializer,
    RetrieveStripeCustomerSerializer,
    CreateCheckoutSessionSerializer,
    ChangePlanSerializer,
)
from .permissions import IsWorkspaceMember


# Custom SessionAuthentication without CSRF for API endpoints
class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # Don't enforce CSRF


# Initialize Stripe
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
logger = logging.getLogger(__name__)


@extend_schema(
    summary="🏢 Get workspace Stripe info",
    description="""
    Retrieve Stripe customer information for a workspace.
    
    **🔐 Permission Requirements**:
    - User must be authenticated
    - User must be a member of the workspace
    
    **📊 Returns**:
    - Workspace details with Stripe customer ID
    - Flag indicating if Stripe customer exists
    """,
    request=None,
    responses={
        200: OpenApiResponse(
            response=StripeCustomerSerializer,
            description="✅ Workspace Stripe info retrieved",
            examples=[
                OpenApiExample(
                    'With Stripe Customer',
                    value={
                        'id': 'workspace-uuid',
                        'workspace_name': 'My Company',
                        'stripe_customer_id': 'cus_PqRsTuVwXyZ123',
                        'has_stripe_customer': True
                    }
                ),
                OpenApiExample(
                    'Without Stripe Customer',
                    value={
                        'id': 'workspace-uuid',
                        'workspace_name': 'My Company',
                        'stripe_customer_id': None,
                        'has_stripe_customer': False
                    }
                )
            ]
        ),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 Not a member of this workspace"),
        404: OpenApiResponse(description="🚫 Workspace not found")
    },
    tags=["Payment Management"]
)
@api_view(['GET'])
@permission_classes([IsWorkspaceMember])
def get_workspace_stripe_info(request, workspace_id):
    """Get Stripe customer info for a workspace"""
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        serializer = StripeCustomerSerializer(workspace)
        return Response(serializer.data)
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )


@extend_schema(
    summary="💳 Create Stripe customer",
    description="""
    Create a new Stripe customer for a workspace.
    
    **🔐 Permission Requirements**:
    - User must be authenticated
    - User must be a member of the workspace
    - Workspace must not already have a Stripe customer
    
    **📝 Process**:
    1. Creates customer in Stripe
    2. Stores customer ID in workspace
    3. Returns customer details
    """,
    request=CreateStripeCustomerSerializer,
    responses={
        201: OpenApiResponse(
            description="✅ Stripe customer created successfully",
            examples=[
                OpenApiExample(
                    'Customer Created',
                    value={
                        'stripe_customer_id': 'cus_PqRsTuVwXyZ123',
                        'email': 'workspace@example.com',
                        'created': 1234567890
                    }
                )
            ]
        ),
        400: OpenApiResponse(
            description="❌ Validation error or customer already exists",
            examples=[
                OpenApiExample(
                    'Already Exists',
                    value={'error': 'Workspace already has a Stripe customer'}
                )
            ]
        ),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 Not a member of this workspace"),
        500: OpenApiResponse(description="❌ Stripe API error")
    },
    tags=["Payment Management"]
)
@api_view(['POST'])
@authentication_classes([TokenAuthentication, CsrfExemptSessionAuthentication])
@permission_classes([IsWorkspaceMember])
def create_stripe_customer(request):
    """Create a Stripe customer for a workspace"""
    serializer = CreateStripeCustomerSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    workspace_id = serializer.validated_data['workspace_id']
    
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        
        # Check if already has Stripe customer
        if workspace.stripe_customer_id:
            return Response(
                {"error": "Workspace already has a Stripe customer"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create customer in Stripe
        customer_data = {
            'metadata': {
                'workspace_id': str(workspace.id),
                'workspace_name': workspace.workspace_name
            }
        }
        
        # Add optional fields
        if 'email' in serializer.validated_data:
            customer_data['email'] = serializer.validated_data['email']
        if 'name' in serializer.validated_data:
            customer_data['name'] = serializer.validated_data['name']
        
        customer = stripe.Customer.create(**customer_data)
        
        # Save customer ID to workspace
        workspace.stripe_customer_id = customer.id
        workspace.save()
        
        return Response({
            'stripe_customer_id': customer.id,
            'email': customer.email,
            'created': customer.created
        }, status=status.HTTP_201_CREATED)
        
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        return Response(
            {"error": f"Stripe error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="🌐 Create customer portal session",
    description="""
    Create a Stripe Customer Portal session for workspace billing management.
    
    **🔐 Permission Requirements**:
    - User must be authenticated
    - User must be a member of the workspace
    - Workspace must have a Stripe customer
    
    **🎯 Portal Features**:
    - View/download invoices
    - Update payment methods
    - View subscription details
    - Update billing address
    """,
    request=StripePortalSessionSerializer,
    responses={
        200: OpenApiResponse(
            description="✅ Portal session created",
            examples=[
                OpenApiExample(
                    'Portal URL',
                    value={
                        'url': 'https://billing.stripe.com/p/session/xyz123',
                        'expires_at': 1234567890
                    }
                )
            ]
        ),
        400: OpenApiResponse(
            description="❌ Validation error",
            examples=[
                OpenApiExample(
                    'No Customer',
                    value={'error': "This workspace doesn't have a Stripe customer yet"}
                )
            ]
        ),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 Not a member of this workspace"),
        500: OpenApiResponse(description="❌ Stripe API error")
    },
    tags=["Payment Management"]
)
@api_view(['POST'])
@authentication_classes([TokenAuthentication, CsrfExemptSessionAuthentication])
@permission_classes([IsWorkspaceMember])
def create_customer_portal_session(request):
    """Create a Stripe customer portal session"""
    serializer = StripePortalSessionSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    workspace_id = serializer.validated_data['workspace_id']
    
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        
        if not workspace.stripe_customer_id:
            return Response(
                {"error": "This workspace doesn't have a Stripe customer yet"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create portal session
        session_data = {
            'customer': workspace.stripe_customer_id,
        }
        
        # Add return URL if provided
        if 'return_url' in serializer.validated_data:
            session_data['return_url'] = serializer.validated_data['return_url']
        
        session = stripe.billing_portal.Session.create(**session_data)
        
        return Response({
            'url': session.url
        })
        
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        return Response(
            {"error": f"Stripe error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="📋 Retrieve Stripe customer details",
    description="""
    Get detailed information about a workspace's Stripe customer.
    
    **🔐 Permission Requirements**:
    - User must be authenticated
    - User must be a member of the workspace
    
    **📊 Returns**:
    - Full Stripe customer object
    - Payment methods
    - Balance information
    """,
    request=RetrieveStripeCustomerSerializer,
    responses={
        200: OpenApiResponse(
            description="✅ Customer details retrieved",
            examples=[
                OpenApiExample(
                    'Customer Details',
                    value={
                        'id': 'cus_PqRsTuVwXyZ123',
                        'email': 'workspace@example.com',
                        'created': 1234567890,
                        'currency': 'usd',
                        'balance': 0,
                        'delinquent': False,
                        'metadata': {
                            'workspace_id': 'workspace-uuid',
                            'workspace_name': 'My Company'
                        }
                    }
                )
            ]
        ),
        400: OpenApiResponse(description="❌ No Stripe customer exists"),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 Not a member of this workspace"),
        404: OpenApiResponse(description="🚫 Workspace not found"),
        500: OpenApiResponse(description="❌ Stripe API error")
    },
    tags=["Payment Management"]
)
@api_view(['POST'])
@authentication_classes([TokenAuthentication, CsrfExemptSessionAuthentication])
@permission_classes([IsWorkspaceMember])
def retrieve_stripe_customer(request):
    """Retrieve Stripe customer details for a workspace"""
    serializer = RetrieveStripeCustomerSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    workspace_id = serializer.validated_data['workspace_id']
    
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        
        if not workspace.stripe_customer_id:
            return Response(
                {"error": "This workspace doesn't have a Stripe customer yet"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Retrieve customer from Stripe
        customer = stripe.Customer.retrieve(workspace.stripe_customer_id)
        
        # Convert to dict and remove sensitive fields
        customer_data = {
            'id': customer.id,
            'email': customer.email,
            'name': customer.name,
            'created': customer.created,
            'currency': customer.currency,
            'balance': customer.balance,
            'delinquent': customer.delinquent,
            'metadata': customer.metadata,
        }
        
        return Response(customer_data)
        
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        return Response(
            {"error": f"Stripe error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) 


@extend_schema(
    summary="📦 List all Stripe products and prices",
    description="""
    Returns all active Stripe products and their prices (monthly/yearly).
    
    **🔐 Permission Requirements**:
    - User must be authenticated
    - (Optional: Staff only, if gewünscht)
    """,
    responses={
        200: OpenApiResponse(
            description="✅ List of Stripe products and prices",
            examples=[
                OpenApiExample(
                    'Products',
                    value={
                        'products': [
                            {
                                'id': 'prod_123',
                                'name': 'Pro Plan',
                                'description': 'Best plan',
                                'prices': [
                                    {
                                        'id': 'price_abc',
                                        'unit_amount': 1900,
                                        'currency': 'eur',
                                        'recurring': {'interval': 'month'}
                                    }
                                ]
                            }
                        ]
                    }
                )
            ]
        ),
        401: OpenApiResponse(description="🚫 Authentication required")
    },
    tags=["Payment Management"]
)
@api_view(['GET'])
@permission_classes([AllowAny])
def list_stripe_products(request):
    """List all Stripe products and their prices"""
    import stripe
    from django.conf import settings
    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')

    # Get all active products
    products = stripe.Product.list(active=True, limit=100)
    # Get all prices (for all products)
    prices = stripe.Price.list(active=True, limit=100)

    # Map prices to products
    price_map = {}
    for price in prices['data']:
        product_id = price['product']
        price_map.setdefault(product_id, []).append({
            'id': price['id'],
            'unit_amount': price['unit_amount'],
            'currency': price['currency'],
            'recurring': price.get('recurring'),
            'nickname': price.get('nickname'),
        })

    result = []
    for product in products['data']:
        result.append({
            'id': product['id'],
            'name': product['name'],
            'description': product.get('description'),
            'active': product['active'],
            'prices': price_map.get(product['id'], [])
        })

    return Response({'products': result})


@extend_schema(
    summary="💳 Create Stripe checkout session",
    description="""
    Create a Stripe Checkout session for subscription payment.
    
    **🔐 Permission Requirements**:
    - User must be authenticated
    - User must be a member of the workspace
    - Workspace must have a Stripe customer
    
    **🎯 Process**:
    1. Creates checkout session with selected price
    2. Returns checkout URL
    3. User completes payment on Stripe Checkout page
    4. After payment, user is redirected to success_url
    5. Webhook updates subscription status
    """,
    request=CreateCheckoutSessionSerializer,
    responses={
        200: OpenApiResponse(
            description="✅ Checkout session created",
            examples=[
                OpenApiExample(
                    'Checkout URL',
                    value={
                        'checkout_url': 'https://checkout.stripe.com/pay/cs_xxx',
                        'session_id': 'cs_xxx'
                    }
                )
            ]
        ),
        400: OpenApiResponse(
            description="❌ Validation error",
            examples=[
                OpenApiExample(
                    'No Customer',
                    value={'error': 'Workspace needs a Stripe customer first'}
                )
            ]
        ),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 Not a member of this workspace"),
        500: OpenApiResponse(description="❌ Stripe API error")
    },
    tags=["Payment Management"]
)
@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def create_checkout_session(request):
    """Create Stripe checkout session for subscription"""
    serializer = CreateCheckoutSessionSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    workspace_id = serializer.validated_data['workspace_id']
    price_id = serializer.validated_data['price_id']
    success_url = serializer.validated_data['success_url']
    cancel_url = serializer.validated_data['cancel_url']
    
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        
        # Do NOT cancel existing subscriptions here. Plan changes should be handled via the dedicated change-plan endpoint or the billing portal.
        
        # Create checkout session - customer will be created automatically if needed
        session_params = {
            'payment_method_types': ['card'],
            'line_items': [{
                'price': price_id,
                'quantity': 1,
            }],
            'mode': 'subscription',
            'success_url': success_url + '?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': cancel_url,
            'client_reference_id': str(workspace.id),
            'metadata': {
                'workspace_id': str(workspace.id),
                'workspace_name': workspace.workspace_name,
                'payer_user_id': str(getattr(request.user, 'id', '')),
                'payer_email': getattr(request.user, 'email', '') or ''
            }
        }
        
        # If workspace already has a customer, use it
        if workspace.stripe_customer_id:
            session_params['customer'] = workspace.stripe_customer_id
        
        session = stripe.checkout.Session.create(**session_params)
        print(f"✅ Created checkout session {session.id} for price {price_id}")
        
        return Response({
            'checkout_url': session.url,
            'session_id': session.id
        })
        
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        return Response(
            {"error": f"Stripe error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="🧾 Create Stripe checkout for 100-minute pack (one-time)",
    description="Creates a Stripe Checkout Session to purchase a 100-minute pack as a one-time payment.",
    tags=["Payment Management"]
)
@api_view(['POST'])
@authentication_classes([TokenAuthentication, CsrfExemptSessionAuthentication])
@permission_classes([IsWorkspaceMember])
def create_minute_pack_checkout(request):
    """Create Stripe Checkout Session for one-time 100-minute pack purchase."""
    try:
        workspace_id = request.data.get('workspace_id')
        if not workspace_id:
            return Response({"error": "workspace_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        price_id = getattr(settings, 'STRIPE_MINUTE_PACK_PRICE_ID', '')
        if not price_id:
            return Response({"error": "STRIPE_MINUTE_PACK_PRICE_ID is not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        workspace = Workspace.objects.get(id=workspace_id)

        success_url = f"{settings.SITE_URL}/dashboard/settings?tab=billing&topup=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{settings.SITE_URL}/dashboard/settings?tab=billing&topup=cancelled"

        session_params = {
            'payment_method_types': ['card'],
            'mode': 'payment',
            'line_items': [{
                'price': price_id,
                'quantity': 1,
            }],
            'success_url': success_url,
            'cancel_url': cancel_url,
            'client_reference_id': str(workspace.id),
            'metadata': {
                'workspace_id': str(workspace.id),
                'reason': 'minute_pack',
                'minutes': '100',
            },
        }

        if workspace.stripe_customer_id:
            session_params['customer'] = workspace.stripe_customer_id

        session = stripe.checkout.Session.create(**session_params)
        return Response({
            'checkout_url': session.url,
            'session_id': session.id,
        })
    except Workspace.DoesNotExist:
        return Response({"error": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND)
    except stripe.error.StripeError as e:
        return Response({"error": f"Stripe error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(
    summary="🔄 Change subscription plan (price)",
    description="Update the current Stripe subscription to a new price with proper proration.",
    request=ChangePlanSerializer,
    responses={
        200: OpenApiResponse(description="✅ Plan changed"),
        400: OpenApiResponse(description="❌ Validation error"),
        404: OpenApiResponse(description="🚫 Workspace not found"),
        500: OpenApiResponse(description="❌ Stripe API error"),
    },
    tags=["Payment Management"]
)
@api_view(['POST'])
@authentication_classes([TokenAuthentication, CsrfExemptSessionAuthentication])
@permission_classes([IsWorkspaceMember])
def change_subscription_plan(request):
    """Change the current plan by updating the subscription item's price with proration."""
    serializer = ChangePlanSerializer(data=request.data, context={'request': request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    workspace_id = serializer.validated_data['workspace_id']
    price_id = serializer.validated_data['price_id']
    proration_behavior = serializer.validated_data.get('proration_behavior', 'create_prorations')
    payment_behavior = serializer.validated_data.get('payment_behavior', 'pending_if_incomplete')

    try:
        workspace = Workspace.objects.get(id=workspace_id)
        if not workspace.stripe_subscription_id:
            return Response({"error": "No active subscription found"}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve subscription to get current item id
        subscription = stripe.Subscription.retrieve(workspace.stripe_subscription_id)
        items = subscription['items']['data']
        if not items:
            return Response({"error": "Subscription has no items"}, status=status.HTTP_400_BAD_REQUEST)

        current_item_id = items[0]['id']

        updated = stripe.Subscription.modify(
            workspace.stripe_subscription_id,
            proration_behavior=proration_behavior,
            payment_behavior=payment_behavior,
            items=[{
                'id': current_item_id,
                'price': price_id,
            }]
        )

        # Return a concise status; webhook will reconcile DB records
        return Response({
            'id': updated['id'],
            'status': updated['status'],
            'cancel_at_period_end': updated.get('cancel_at_period_end', False),
            'current_period_end': updated.get('current_period_end'),
            'price_id': updated['items']['data'][0]['price']['id'] if updated['items']['data'] else None,
        })
    except Workspace.DoesNotExist:
        return Response({"error": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND)
    except stripe.error.StripeError as e:
        return Response({"error": f"Stripe error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    summary="📊 Get workspace subscription status",
    description="""
    Get the current subscription status for a workspace.
    
    **🔐 Permission Requirements**:
    - User must be authenticated
    - User must be a member of the workspace
    
    **📊 Returns**:
    - Current subscription details
    - Plan information
    - Next billing date
    - Subscription status
    """,
    responses={
        200: OpenApiResponse(
            description="✅ Subscription details retrieved",
            examples=[
                OpenApiExample(
                    'Active Subscription',
                    value={
                        'has_subscription': True,
                        'subscription': {
                            'id': 'sub_xxx',
                            'status': 'active',
                            'current_period_end': 1234567890,
                            'cancel_at_period_end': False,
                            'plan': {
                                'id': 'price_xxx',
                                'product': 'prod_xxx',
                                'amount': 4900,
                                'currency': 'eur',
                                'interval': 'month'
                            }
                        }
                    }
                ),
                OpenApiExample(
                    'No Subscription',
                    value={
                        'has_subscription': False,
                        'subscription': None
                    }
                )
            ]
        ),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 Not a member of this workspace"),
        404: OpenApiResponse(description="🚫 Workspace not found")
    },
    tags=["Payment Management"]
)
@api_view(['GET'])
@permission_classes([IsWorkspaceMember])
def get_subscription_status(request, workspace_id):
    """Get current subscription status for workspace"""
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        
        if not workspace.stripe_customer_id:
            return Response({
                'has_subscription': False,
                'subscription': None
            })
        # Retrieve subscription robustly: prefer known ID, otherwise find latest
        subscription = None
        try:
            if workspace.stripe_subscription_id:
                subscription = stripe.Subscription.retrieve(workspace.stripe_subscription_id)
        except stripe.error.StripeError:
            subscription = None

        if subscription is None:
            # Try active first
            subs_active = stripe.Subscription.list(customer=workspace.stripe_customer_id, status='active', limit=1)
            if subs_active['data']:
                subscription = subs_active['data'][0]
            else:
                # Fallback to any latest subscription
                subs_any = stripe.Subscription.list(customer=workspace.stripe_customer_id, limit=1)
                if subs_any['data']:
                    subscription = subs_any['data'][0]

        if subscription is not None:
            stripe_status = subscription.status
            if stripe_status == 'trialing':
                stripe_status = 'trial'

            workspace.stripe_subscription_id = subscription.id
            workspace.subscription_status = stripe_status
            workspace.save()

            has_sub = stripe_status not in ['canceled', 'cancelled', 'incomplete_expired']

            # Normalize fields; ensure epoch seconds and booleans present
            current_period_end = getattr(subscription, 'current_period_end', None)
            cancel_at_period_end = bool(getattr(subscription, 'cancel_at_period_end', False))

            return Response({
                'has_subscription': bool(has_sub),
                'subscription': {
                    'id': subscription.id,
                    'status': stripe_status,
                    'current_period_end': current_period_end,
                    'cancel_at_period_end': cancel_at_period_end,
                    'plan': {
                        'id': subscription['items']['data'][0]['price']['id'],
                        'product': subscription['items']['data'][0]['price']['product'],
                        'amount': subscription['items']['data'][0]['price']['unit_amount'],
                        'currency': subscription['items']['data'][0]['price']['currency'],
                        'interval': subscription['items']['data'][0]['price']['recurring']['interval']
                    }
                }
            })

        # Kein Abo vorhanden
        workspace.subscription_status = 'none'
        workspace.save()

        return Response({
            'has_subscription': False,
            'subscription': None
        })
            
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        return Response(
            {"error": f"Stripe error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="🚫 Cancel subscription",
    description="""
    Cancel the workspace subscription at the end of the billing period.
    
    **🔐 Permission Requirements**:
    - User must be authenticated
    - User must be a member of the workspace
    - Workspace must have an active subscription
    
    **⚠️ Note**:
    - Subscription remains active until end of billing period
    - Can be reactivated before period ends
    """,
    responses={
        200: OpenApiResponse(
            description="✅ Subscription cancelled",
            examples=[
                OpenApiExample(
                    'Cancelled',
                    value={
                        'message': 'Subscription will be cancelled at period end',
                        'cancel_at': 1234567890
                    }
                )
            ]
        ),
        400: OpenApiResponse(description="❌ No active subscription"),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 Not a member of this workspace"),
        404: OpenApiResponse(description="🚫 Workspace not found")
    },
    tags=["Payment Management"]
)
@api_view(['POST'])
@permission_classes([IsWorkspaceMember])
def cancel_subscription(request, workspace_id):
    """Cancel workspace subscription"""
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        
        if not workspace.stripe_subscription_id:
            return Response(
                {"error": "No active subscription"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Cancel at period end
        subscription = stripe.Subscription.modify(
            workspace.stripe_subscription_id,
            cancel_at_period_end=True
        )
        
        # Do not mark as cancelled immediately; final state will be reconciled via webhook.
        # Keep DB status as-is; clients can read cancel_at_period_end from Stripe via status endpoint.
        
        return Response({
            'message': 'Subscription will be cancelled at period end',
            'cancel_at': subscription.current_period_end
        })
        
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        return Response(
            {"error": f"Stripe error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="✅ Resume subscription (undo cancel)",
    description="Resume a subscription by unsetting cancel_at_period_end so it continues next period.",
    responses={
        200: OpenApiResponse(description="✅ Subscription resumed"),
        400: OpenApiResponse(description="❌ No active subscription or not scheduled to cancel"),
        404: OpenApiResponse(description="🚫 Workspace not found"),
        500: OpenApiResponse(description="❌ Stripe API error"),
    },
    tags=["Payment Management"]
)
@api_view(['POST'])
@permission_classes([IsWorkspaceMember])
def resume_subscription(request, workspace_id):
    """Undo cancel_at_period_end on the current subscription"""
    try:
        workspace = Workspace.objects.get(id=workspace_id)

        if not workspace.stripe_subscription_id:
            return Response(
                {"error": "No active subscription"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Retrieve existing subscription to check flag
        subscription = stripe.Subscription.retrieve(workspace.stripe_subscription_id)
        if not getattr(subscription, 'cancel_at_period_end', False):
            return Response(
                {"message": "Subscription is not set to cancel at period end"},
                status=status.HTTP_200_OK
            )

        updated = stripe.Subscription.modify(
            workspace.stripe_subscription_id,
            cancel_at_period_end=False
        )

        # Do not force DB status; webhook will reconcile.
        return Response({
            'message': 'Subscription resumed',
            'cancel_at_period_end': updated.cancel_at_period_end,
            'current_period_end': updated.current_period_end,
            'status': updated.status,
        })

    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        return Response(
            {"error": f"Stripe error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="🔗 Stripe webhook handler",
    description="Handle incoming Stripe webhook events",
    auth=None  # No authentication for webhooks
)
@csrf_exempt
@api_view(['POST'])
@permission_classes([])  # No permission check for webhooks
def stripe_webhook(request):
    """Handle Stripe webhook events"""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
    
    logger.info("Stripe webhook received; payload_len=%s, has_sig=%s, has_secret=%s", len(payload), bool(sig_header), bool(webhook_secret))
    
    if not webhook_secret:
        logger.error("Webhook secret not configured")
        return Response(
            {"error": "Webhook secret not configured"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        logger.info("Webhook signature verified successfully")
    except ValueError as e:
        # Invalid payload
        logger.warning("Invalid payload: %s", e)
        return Response(
            {"error": "Invalid payload"},
            status=status.HTTP_400_BAD_REQUEST
        )
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.warning("Invalid signature: %s", e)
        return Response(
            {"error": "Invalid signature"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Handle the event
    event_type = event['type']
    event_data = event['data']['object']
    event_id = event.get('id', 'unknown')

    # Idempotency guard using cache (no DB migration required)
    cache_key = f"stripe_event:{event_id}"
    if cache.get(cache_key):
        logger.info("Duplicate webhook event ignored; id=%s type=%s", event_id, event_type)
        return Response({"received": True, "duplicate": True}, status=status.HTTP_200_OK)
    # Mark as processed for 7 days
    cache.set(cache_key, True, timeout=7*24*3600)

    logger.info("Processing webhook; id=%s type=%s", event_id, event_type)
    
    # Customer events
    if event_type == 'customer.created':
        # Customer was created in Stripe
        customer_id = event_data['id']
        metadata = event_data.get('metadata', {})
        workspace_id = metadata.get('workspace_id')
        
        if workspace_id:
            try:
                workspace = Workspace.objects.get(id=workspace_id)
                if not workspace.stripe_customer_id:
                    workspace.stripe_customer_id = customer_id
                    workspace.save()
                    print(f"Updated workspace {workspace_id} with Stripe customer {customer_id}")
            except Workspace.DoesNotExist:
                print(f"Workspace {workspace_id} not found for customer {customer_id}")
    
    elif event_type == 'customer.updated':
        # Customer was updated in Stripe
        customer_id = event_data['id']
        print(f"Customer {customer_id} was updated")
    
    elif event_type == 'customer.deleted':
        # Customer was deleted in Stripe
        customer_id = event_data['id']
        try:
            workspace = Workspace.objects.get(stripe_customer_id=customer_id)
            workspace.stripe_customer_id = None
            workspace.save()
            print(f"Removed Stripe customer from workspace {workspace.id}")
        except Workspace.DoesNotExist:
            print(f"No workspace found for deleted customer {customer_id}")
    
    # Payment events
    elif event_type == 'payment_intent.succeeded':
        # Payment was successful
        payment_intent = event_data
        customer_id = payment_intent.get('customer')
        amount = payment_intent['amount'] / 100  # Convert from cents
        currency = payment_intent['currency']
        print(f"Payment succeeded: {amount} {currency} from customer {customer_id}")
    
    elif event_type == 'payment_intent.failed':
        # Payment failed
        payment_intent = event_data
        customer_id = payment_intent.get('customer')
        print(f"Payment failed for customer {customer_id}")
    
    # Invoice events
    elif event_type == 'invoice.paid':
        # Invoice was paid
        invoice = event_data
        customer_id = invoice['customer']
        amount = invoice['amount_paid'] / 100
        currency = invoice['currency']
        print(f"Invoice paid: {amount} {currency} by customer {customer_id}")
    
    elif event_type == 'invoice.payment_failed':
        # Invoice payment failed
        invoice = event_data
        customer_id = invoice['customer']
        print(f"Invoice payment failed for customer {customer_id}")
    
    # Checkout completed
    elif event_type == 'checkout.session.completed':
        session = event_data
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        metadata = session.get('metadata', {})
        workspace_id = metadata.get('workspace_id') or session.get('client_reference_id')
        reason = metadata.get('reason')
        
        logger.info("checkout.session.completed customer=%s subscription=%s workspace=%s meta=%s client_ref=%s",
                    customer_id, subscription_id, workspace_id, metadata, session.get('client_reference_id'))
        
        # Minute pack one-time payment via our custom Checkout: credit minutes
        if reason == 'minute_pack' and workspace_id:
            try:
                from core.quotas import get_usage_container
                workspace = Workspace.objects.get(id=workspace_id)
                # Ensure select_for_update is used inside a transaction
                with transaction.atomic():
                    usage = get_usage_container(workspace)
                    # Idempotency per session/payment intent handled by global event id cache above
                    usage.extra_call_minutes = (usage.extra_call_minutes or 0) + 100
                    usage.save()
                logger.info("Credited 100 minutes to workspace %s via minute pack", workspace_id)
            except Exception as e:
                logger.exception("Failed to credit minute pack for workspace %s: %s", workspace_id, e)
            return Response({"received": True})

        # Minute pack purchased via Stripe Customer Portal (no metadata):
        # Detect by matching price_id or product_id from line items
        try:
            minute_pack_price_id = getattr(settings, 'STRIPE_MINUTE_PACK_PRICE_ID', '')
            minute_pack_product_id = getattr(settings, 'STRIPE_MINUTE_PACK_PRODUCT_ID', '')
        except Exception:
            minute_pack_price_id = ''
            minute_pack_product_id = ''

        if minute_pack_price_id or minute_pack_product_id:
            try:
                # Retrieve full session with line items expanded
                full_session = stripe.checkout.Session.retrieve(
                    session.get('id'),
                    expand=['line_items.data.price.product']
                )
                line_items = (full_session.get('line_items') or {}).get('data', [])
            except Exception as e:
                logger.warning("Failed to retrieve/expand checkout.session %s: %s", session.get('id'), e)
                line_items = []

            total_packs = 0
            for item in line_items:
                price = item.get('price') or {}
                price_id = price.get('id')
                product = price.get('product')
                # product can be an ID string or expanded dict
                product_id = None
                if isinstance(product, str):
                    product_id = product
                elif isinstance(product, dict):
                    product_id = product.get('id')

                is_minute_pack = (
                    (minute_pack_price_id and price_id == minute_pack_price_id) or
                    (minute_pack_product_id and product_id == minute_pack_product_id)
                )
                if is_minute_pack:
                    qty = int(item.get('quantity') or 1)
                    total_packs += max(qty, 0)

            if total_packs > 0:
                try:
                    from core.quotas import get_usage_container
                    # Determine workspace by metadata or by Stripe customer mapping
                    workspace = None
                    if workspace_id:
                        workspace = Workspace.objects.get(id=workspace_id)
                    elif customer_id:
                        workspace = Workspace.objects.get(stripe_customer_id=customer_id)
                        workspace_id = str(workspace.id)

                    if workspace is not None:
                        # Ensure select_for_update is used inside a transaction
                        with transaction.atomic():
                            usage = get_usage_container(workspace)
                            credited_minutes = 100 * total_packs
                            usage.extra_call_minutes = (usage.extra_call_minutes or 0) + credited_minutes
                            usage.save()
                        logger.info(
                            "Credited %s minutes to workspace %s via portal minute pack (packs=%s)",
                            credited_minutes, workspace_id, total_packs
                        )
                        return Response({"received": True})
                    else:
                        logger.warning(
                            "Unable to resolve workspace for portal minute pack; customer=%s workspace_in_meta=%s",
                            customer_id, workspace_id
                        )
                except Workspace.DoesNotExist:
                    logger.warning("Workspace not found for portal minute pack; customer=%s", customer_id)
                except Exception as e:
                    logger.exception("Failed to credit portal minute pack: %s", e)

        if workspace_id and subscription_id:
            try:
                workspace = Workspace.objects.get(id=workspace_id)
                logger.info("Found workspace: %s (%s)", workspace.workspace_name, workspace.id)
                
                workspace.stripe_subscription_id = subscription_id
                workspace.subscription_status = 'active'
                # Save customer ID if not yet stored
                if customer_id and not workspace.stripe_customer_id:
                    workspace.stripe_customer_id = customer_id
                    logger.info("Setting customer ID for workspace=%s", workspace.id)
                
                # Get subscription details to find the plan
                subscription = stripe.Subscription.retrieve(subscription_id)
                # Map Stripe status trialing -> our trial
                sub_status = subscription.status
                if sub_status == 'trialing':
                    sub_status = 'trial'
                workspace.subscription_status = sub_status
                logger.info("Setting subscription status=%s for workspace=%s", sub_status, workspace.id)

                if subscription['items']['data']:
                    price_id = subscription['items']['data'][0]['price']['id']
                    print(f"💰 Price ID: {price_id}")
                    # Try to match with a plan
                    from core.models import Plan, WorkspaceSubscription
                    plan = Plan.objects.filter(
                        stripe_price_id_monthly=price_id
                    ).first() or Plan.objects.filter(
                        stripe_price_id_yearly=price_id
                    ).first()
                    
                    if plan:
                        # Create WorkspaceSubscription record (this is what the quota system expects!)
                        from datetime import datetime, timezone
                        
                        # Deactivate any existing subscriptions
                        WorkspaceSubscription.objects.filter(
                            workspace=workspace,
                            is_active=True
                        ).update(is_active=False)
                        
                        # Create new active subscription
                        WorkspaceSubscription.objects.create(
                            workspace=workspace,
                            plan=plan,
                            started_at=datetime.now(timezone.utc),
                            is_active=True
                        )
                        
                        logger.info("Created WorkspaceSubscription plan=%s for workspace=%s", plan.plan_name, workspace.id)
                    else:
                        logger.warning("No plan found for price_id=%s", price_id)
                
                workspace.save()
                logger.info("Workspace updated; subscription %s activated for workspace %s", subscription_id, workspace_id)

                # Automatically add payer to workspace and make admin per policy
                try:
                    payer_user_id = metadata.get('payer_user_id') if isinstance(metadata, dict) else None
                    if payer_user_id:
                        payer_user = User.objects.filter(id=payer_user_id).first()
                        if payer_user:
                            # Ensure membership
                            if not workspace.users.filter(id=payer_user.id).exists():
                                workspace.users.add(payer_user)
                                logger.info("Added payer user %s to workspace %s", payer_user.id, workspace.id)

                            # Assign admin depending on setting or if no admin yet
                            auto_assign = getattr(settings, 'PAYMENT_AUTO_ASSIGN_PAYER_AS_ADMIN', True)
                            if auto_assign or not getattr(workspace, 'admin_user_id', None):
                                workspace.admin_user = payer_user
                                workspace.save()
                                logger.info("Assigned payer user %s as admin for workspace %s", payer_user.id, workspace.id)
                except Exception as admin_e:
                    logger.warning("Failed to auto-assign payer as admin for workspace %s: %s", workspace.id, admin_e)
            except Workspace.DoesNotExist:
                logger.error("Workspace not found for checkout session; workspace_id=%s", workspace_id)
            except Exception as e:
                logger.exception("Error updating workspace after checkout: %s", e)
        else:
            logger.warning("Missing data in checkout.session.completed workspace_id=%s subscription_id=%s", workspace_id, subscription_id)
    
    # Subscription events
    elif event_type == 'customer.subscription.created':
        subscription = event_data
        customer_id = subscription['customer']
        subscription_status = subscription['status']
        if subscription_status == 'trialing':
            subscription_status = 'trial'
        
        # Update workspace subscription status
        try:
            workspace = Workspace.objects.get(stripe_customer_id=customer_id)
            workspace.stripe_subscription_id = subscription['id']
            workspace.subscription_status = subscription_status
            # WorkspaceSubscription creation is handled by checkout.session.completed - don't duplicate here!
            workspace.save()
            logger.info("Subscription %s created for workspace %s – status=%s", subscription['id'], workspace.id, subscription_status)
        except Workspace.DoesNotExist:
            logger.warning("No workspace found for subscription.created – customer=%s", customer_id)
    
    elif event_type == 'customer.subscription.updated':
        subscription = event_data
        customer_id = subscription['customer']
        subscription_status = subscription['status']
        if subscription_status == 'trialing':
            subscription_status = 'trial'
        
        # Update workspace subscription status
        try:
            workspace = Workspace.objects.get(stripe_customer_id=customer_id)
            workspace.subscription_status = subscription_status
            workspace.save()
            logger.info("Updated workspace subscription status to %s", subscription_status)

            # Sync WorkspaceSubscription plan mapping on price change
            try:
                items = subscription['items']['data']
                if items:
                    price_id = items[0]['price']['id']
                    from core.models import Plan, WorkspaceSubscription
                    plan = Plan.objects.filter(
                        stripe_price_id_monthly=price_id
                    ).first() or Plan.objects.filter(
                        stripe_price_id_yearly=price_id
                    ).first()
                    if plan:
                        # Deactivate existing active subscriptions
                        WorkspaceSubscription.objects.filter(
                            workspace=workspace,
                            is_active=True
                        ).update(is_active=False)
                        # Create/activate new mapping
                        from datetime import datetime, timezone
                        WorkspaceSubscription.objects.create(
                            workspace=workspace,
                            plan=plan,
                            started_at=datetime.now(timezone.utc),
                            is_active=True
                        )
                        logger.info("Synchronized WorkspaceSubscription to plan %s via subscription.updated", plan.plan_name)
            except Exception as e:
                logger.warning("Failed to sync WorkspaceSubscription on subscription.updated: %s", e)
        except Workspace.DoesNotExist:
            logger.warning("No workspace found for customer %s in subscription.updated", customer_id)
    
    elif event_type == 'customer.subscription.deleted':
        subscription = event_data
        customer_id = subscription['customer']
        
        # Mark subscription as cancelled and deactivate WorkspaceSubscription
        try:
            workspace = Workspace.objects.get(stripe_customer_id=customer_id)
            workspace.subscription_status = 'cancelled'
            workspace.stripe_subscription_id = None
            workspace.save()

            # Deactivate WorkspaceSubscription records
            from core.models import WorkspaceSubscription
            WorkspaceSubscription.objects.filter(
                workspace=workspace,
                is_active=True
            ).update(is_active=False)
            logger.info("Subscription cancelled for workspace %s - deactivated WorkspaceSubscription records", workspace.id)
        except Workspace.DoesNotExist:
            logger.warning("No workspace found for customer %s in subscription.deleted", customer_id)
    
    else:
        # Unhandled event type
        logger.info("Unhandled Stripe event type: %s", event_type)
    
    # Return success response
    return Response({"received": True}, status=status.HTTP_200_OK) 


@extend_schema(
    summary="🔍 Check workspace subscription status",
    description="""
    Check if a workspace has an active subscription.
    
    **Returns**:
    - `has_active_subscription`: Boolean indicating if subscription is active
    - `subscription_status`: Current status (trial, active, cancelled, past_due, unpaid)
    - `subscription_end_date`: When the subscription ends (if active)
    """,
    responses={
        200: OpenApiResponse(
            description="✅ Subscription status retrieved",
            examples=[
                OpenApiExample(
                    'Active Subscription',
                    value={
                        'has_active_subscription': True,
                        'subscription_status': 'active',
                        'subscription_end_date': '2024-12-31T23:59:59Z',
                        'stripe_subscription_id': 'sub_123abc'
                    }
                ),
                OpenApiExample(
                    'No Active Subscription',
                    value={
                        'has_active_subscription': False,
                        'subscription_status': 'trial',
                        'subscription_end_date': None,
                        'stripe_subscription_id': None
                    }
                )
            ]
        ),
        404: OpenApiResponse(description="🚫 Workspace not found")
    },
    tags=["Payment Management"]
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_workspace_subscription(request, workspace_id):
    """Check if workspace has active subscription"""
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        
        # Check if user is member of workspace unless superuser
        if not (getattr(request.user, 'is_superuser', False) or workspace.users.filter(id=request.user.id).exists()):
            return Response(
                {"error": "Not a member of this workspace"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check subscription status
        has_active = workspace.subscription_status in ['active', 'trial']
        
        response_data = {
            'has_active_subscription': has_active,
            'subscription_status': workspace.subscription_status,
            'subscription_end_date': None,
            'stripe_subscription_id': workspace.stripe_subscription_id
        }
        
        # If there's a Stripe subscription, get more details
        if workspace.stripe_subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(workspace.stripe_subscription_id)
                response_data['subscription_end_date'] = subscription.current_period_end
                stripe_status = subscription.status
                if stripe_status == 'trialing':
                    stripe_status = 'trial'
                response_data['subscription_status'] = stripe_status
                response_data['has_active_subscription'] = stripe_status in ['active', 'trial']
            except stripe.error.StripeError:
                pass  # Use database values if Stripe fails
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"},
            status=status.HTTP_404_NOT_FOUND
        )


@extend_schema(
    summary="📊 Get workspace usage and quota status",
    description="""
    Get comprehensive usage and quota information for a workspace.
    
    **🔐 Permission Requirements**:
    - User must be authenticated
    - User must be a member of the workspace
    
    **📊 Returns**:
    - Current usage for all features
    - Plan limits and remaining quotas
    - Billing period information
    - Usage percentages
    """,
    responses={
        200: OpenApiResponse(
            description="✅ Usage status retrieved",
            examples=[
                OpenApiExample(
                    'Usage Status',
                    value={
                        'workspace': {
                            'id': 'workspace-uuid',
                            'name': 'My Company',
                            'plan': 'Pro'
                        },
                        'billing_period': {
                            'start': '2025-01-01T00:00:00Z',
                            'end': '2025-02-01T00:00:00Z',
                            'days_remaining': 15
                        },
                        'features': {
                            'call_minutes': {
                                'used': 234.5,
                                'limit': 1000,
                                'remaining': 765.5,
                                'unlimited': False,
                                'percentage_used': 23.45
                            },
                            'max_agents': {
                                'used': 2,
                                'limit': 3,
                                'remaining': 1,
                                'unlimited': False,
                                'percentage_used': 66.67
                            }
                        }
                    }
                )
            ]
        ),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 Not a member of this workspace"),
        404: OpenApiResponse(description="🚫 Workspace not found")
    },
    tags=["Payment Management"]
)
@api_view(['GET'])
@permission_classes([IsWorkspaceMember])
def get_workspace_usage_status(request, workspace_id):
    """Get comprehensive usage and quota status for workspace"""
    from core.quotas import get_feature_usage_status_readonly, current_billing_window
    from core.models import Feature
    from datetime import datetime, timezone
    
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        
        # Get active subscription for billing period
        subscription = workspace.current_subscription
        if subscription:
            plan = subscription.plan
            period_start, period_end = current_billing_window(subscription)
            
            # Calculate days remaining in billing period
            now = datetime.now(timezone.utc)
            days_remaining = max(0, (period_end - now).days)
        else:
            plan = None
            period_start = period_end = None
            days_remaining = None
        
        # Get all measurable features (only those we support)
        features = Feature.objects.filter(feature_name__in=['call_minutes', 'max_users', 'max_agents'])
        feature_usage = {}
        
        for feature in features:
            # SPECIAL CASE: For max_users, count ACTUAL users in workspace, not quota usage
            if feature.feature_name == 'max_users':
                actual_user_count = workspace.users.count()
                
                # Get limit from plan
                usage_info = get_feature_usage_status_readonly(workspace, feature.feature_name)
                limit = usage_info['limit']
                unlimited = usage_info['unlimited']
                
                remaining = None
                percentage_used = None
                if not unlimited and limit and limit > 0:
                    remaining = max(limit - actual_user_count, 0)
                    percentage_used = float((actual_user_count / limit) * 100)
                    percentage_used = round(percentage_used, 2)
                
                feature_usage[feature.feature_name] = {
                    'used': float(actual_user_count),
                    'limit': float(limit) if limit else None,
                    'remaining': float(remaining) if remaining is not None else None,
                    'unlimited': unlimited,
                    'percentage_used': percentage_used,
                    'unit': feature.unit
                }
            # SPECIAL CASE: For max_agents, count ACTUAL agents in workspace, not quota usage  
            elif feature.feature_name == 'max_agents':
                from core.models import Agent
                actual_agent_count = Agent.objects.filter(workspace=workspace).count()
                
                # Get limit from plan
                usage_info = get_feature_usage_status_readonly(workspace, feature.feature_name)
                limit = usage_info['limit']
                unlimited = usage_info['unlimited']
                
                remaining = None
                percentage_used = None
                if not unlimited and limit and limit > 0:
                    remaining = max(limit - actual_agent_count, 0)
                    percentage_used = float((actual_agent_count / limit) * 100)
                    percentage_used = round(percentage_used, 2)
                
                feature_usage[feature.feature_name] = {
                    'used': float(actual_agent_count),
                    'limit': float(limit) if limit else None,
                    'remaining': float(remaining) if remaining is not None else None,
                    'unlimited': unlimited,
                    'percentage_used': percentage_used,
                    'unit': feature.unit
                }
            else:
                # For other features (like call_minutes), use quota tracking system
                usage_info = get_feature_usage_status_readonly(workspace, feature.feature_name)
                
                # Calculate percentage used if not unlimited
                percentage_used = None
                if not usage_info['unlimited'] and usage_info['limit'] and usage_info['limit'] > 0:
                    percentage_used = float((usage_info['used'] / usage_info['limit']) * 100)
                    percentage_used = round(percentage_used, 2)
                
                feature_usage[feature.feature_name] = {
                    'used': float(usage_info['used']),
                    'limit': float(usage_info['limit']) if usage_info['limit'] else None,
                    'remaining': float(usage_info['remaining']) if usage_info['remaining'] else None,
                    'unlimited': usage_info['unlimited'],
                    'percentage_used': percentage_used,
                    'unit': feature.unit
                }
        
        # Build response
        response_data = {
            'workspace': {
                'id': str(workspace.id),
                'name': workspace.workspace_name,
                'plan': plan.plan_name if plan else None
            },
            'billing_period': {
                'start': period_start.isoformat() if period_start else None,
                'end': period_end.isoformat() if period_end else None,
                'days_remaining': days_remaining
            } if period_start and period_end else None,
            'features': feature_usage
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"},
            status=status.HTTP_404_NOT_FOUND
        ) 


@extend_schema(
    summary="Purchase a 100-minute pack",
    description="Credits 100 extra call minutes to the current billing period for the workspace.",
    responses={
        200: OpenApiResponse(description="✅ Minute pack credited"),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 Not a member of this workspace"),
        404: OpenApiResponse(description="🚫 Workspace not found"),
    },
    tags=["Payment Management"]
)
@api_view(['POST'])
@permission_classes([IsWorkspaceMember])
def purchase_minute_pack(request, workspace_id):
    """Credit a 100-minute pack to the current billing period (simple internal action)."""
    from core.quotas import get_usage_container
    from decimal import Decimal
    try:
        workspace = Workspace.objects.get(id=workspace_id)
    except Workspace.DoesNotExist:
        return Response({"error": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND)

    # Only workspace admin, staff, or superuser should be able to credit minute packs
    if not (request.user.is_superuser or request.user.is_staff or (workspace.admin_user_id and workspace.admin_user_id == request.user.id)):
        return Response({"error": "Only workspace admin can purchase minute packs"}, status=status.HTTP_403_FORBIDDEN)

    try:
        usage = get_usage_container(workspace)
        # Guard in case field does not exist yet
        if not hasattr(usage, 'extra_call_minutes'):
            return Response({"error": "Minute packs not supported on this deployment"}, status=status.HTTP_400_BAD_REQUEST)
        usage.extra_call_minutes = (usage.extra_call_minutes or Decimal('0')) + Decimal('100')
        usage.save(update_fields=['extra_call_minutes', 'updated_at'])
        return Response({
            "message": "Minute pack credited",
            "extra_call_minutes": float(usage.extra_call_minutes)
        }, status=status.HTTP_200_OK)
    except Exception as exc:
        return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 