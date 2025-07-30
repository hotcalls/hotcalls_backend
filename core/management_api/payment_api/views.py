import stripe
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.authentication import TokenAuthentication, BasicAuthentication, SessionAuthentication
from rest_framework.response import Response
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework.permissions import IsAuthenticated, AllowAny

from core.models import Workspace
from .serializers import (
    StripeCustomerSerializer,
    CreateStripeCustomerSerializer,
    StripePortalSessionSerializer,
    RetrieveStripeCustomerSerializer,
    CreateCheckoutSessionSerializer
)
from .permissions import IsWorkspaceMember


# Custom SessionAuthentication without CSRF for API endpoints
class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # Don't enforce CSRF


# Initialize Stripe
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')


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
            'url': session.url,
            'expires_at': session.expires_at
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
@permission_classes([IsWorkspaceMember])
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
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=workspace.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=cancel_url,
            metadata={
                'workspace_id': str(workspace.id),
                'workspace_name': workspace.workspace_name
            }
        )
        
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
        
        # Get active subscriptions
        subscriptions = stripe.Subscription.list(
            customer=workspace.stripe_customer_id,
            status='active',
            limit=1
        )
        
        if subscriptions['data']:
            subscription = subscriptions['data'][0]
            
            # Update workspace subscription status
            workspace.stripe_subscription_id = subscription.id
            workspace.subscription_status = 'active'
            workspace.save()
            
            return Response({
                'has_subscription': True,
                'subscription': {
                    'id': subscription.id,
                    'status': subscription.status,
                    'current_period_end': subscription.current_period_end,
                    'cancel_at_period_end': subscription.cancel_at_period_end,
                    'plan': {
                        'id': subscription['items']['data'][0]['price']['id'],
                        'product': subscription['items']['data'][0]['price']['product'],
                        'amount': subscription['items']['data'][0]['price']['unit_amount'],
                        'currency': subscription['items']['data'][0]['price']['currency'],
                        'interval': subscription['items']['data'][0]['price']['recurring']['interval']
                    }
                }
            })
        else:
            # Check for other statuses
            all_subs = stripe.Subscription.list(
                customer=workspace.stripe_customer_id,
                limit=1
            )
            
            if all_subs['data']:
                sub = all_subs['data'][0]
                workspace.stripe_subscription_id = sub.id
                workspace.subscription_status = sub.status
                workspace.save()
            else:
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
        
        workspace.subscription_status = 'cancelled'
        workspace.save()
        
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
    summary="🔔 Stripe webhook endpoint",
    description="""
    Receive and process Stripe webhook events.
    
    **🔐 Security**:
    - Validates webhook signature
    - No authentication required (Stripe sends directly)
    
    **📊 Handled Events**:
    - checkout.session.completed
    - customer.created
    - customer.updated
    - customer.deleted
    - payment_intent.succeeded
    - payment_intent.failed
    - invoice.paid
    - invoice.payment_failed
    - customer.subscription.created
    - customer.subscription.updated
    - customer.subscription.deleted
    
    **🔄 Process**:
    1. Verify webhook signature
    2. Parse event data
    3. Process based on event type
    4. Return 200 OK
    """,
    request=None,
    responses={
        200: OpenApiResponse(
            description="✅ Webhook processed successfully",
            examples=[
                OpenApiExample(
                    'Success',
                    value={'received': True}
                )
            ]
        ),
        400: OpenApiResponse(
            description="❌ Invalid payload or signature",
            examples=[
                OpenApiExample(
                    'Invalid Signature',
                    value={'error': 'Invalid signature'}
                )
            ]
        ),
        500: OpenApiResponse(description="❌ Processing error")
    },
    tags=["Payment Management"],
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
    
    if not webhook_secret:
        return Response(
            {"error": "Webhook secret not configured"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        # Invalid payload
        return Response(
            {"error": "Invalid payload"},
            status=status.HTTP_400_BAD_REQUEST
        )
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return Response(
            {"error": "Invalid signature"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Handle the event
    event_type = event['type']
    event_data = event['data']['object']
    
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
        workspace_id = metadata.get('workspace_id')
        
        if workspace_id and subscription_id:
            try:
                workspace = Workspace.objects.get(id=workspace_id)
                workspace.stripe_subscription_id = subscription_id
                workspace.subscription_status = 'active'
                
                # Get subscription details to find the plan
                subscription = stripe.Subscription.retrieve(subscription_id)
                if subscription['items']['data']:
                    price_id = subscription['items']['data'][0]['price']['id']
                    # Try to match with a plan
                    from core.models import Plan
                    plan = Plan.objects.filter(
                        stripe_price_id_monthly=price_id
                    ).first() or Plan.objects.filter(
                        stripe_price_id_yearly=price_id
                    ).first()
                    
                    if plan:
                        workspace.current_plan = plan
                
                workspace.save()
                print(f"Subscription {subscription_id} activated for workspace {workspace_id}")
            except Workspace.DoesNotExist:
                print(f"Workspace {workspace_id} not found")
    
    # Subscription events
    elif event_type == 'customer.subscription.created':
        subscription = event_data
        customer_id = subscription['customer']
        print(f"Subscription created for customer {customer_id}")
    
    elif event_type == 'customer.subscription.updated':
        subscription = event_data
        customer_id = subscription['customer']
        subscription_status = subscription['status']
        
        # Update workspace subscription status
        try:
            workspace = Workspace.objects.get(stripe_customer_id=customer_id)
            workspace.subscription_status = subscription_status
            workspace.save()
            print(f"Updated workspace subscription status to {subscription_status}")
        except Workspace.DoesNotExist:
            print(f"No workspace found for customer {customer_id}")
    
    elif event_type == 'customer.subscription.deleted':
        subscription = event_data
        customer_id = subscription['customer']
        
        # Mark subscription as cancelled
        try:
            workspace = Workspace.objects.get(stripe_customer_id=customer_id)
            workspace.subscription_status = 'cancelled'
            workspace.stripe_subscription_id = None
            workspace.save()
            print(f"Subscription cancelled for workspace {workspace.id}")
        except Workspace.DoesNotExist:
            print(f"No workspace found for customer {customer_id}")
    
    else:
        # Unhandled event type
        print(f"Unhandled event type: {event_type}")
    
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
        
        # Check if user is member of workspace
        if not workspace.users.filter(id=request.user.id).exists():
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
                response_data['subscription_status'] = subscription.status
                response_data['has_active_subscription'] = subscription.status == 'active'
            except stripe.error.StripeError:
                pass  # Use database values if Stripe fails
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Workspace.DoesNotExist:
        return Response(
            {"error": "Workspace not found"},
            status=status.HTTP_404_NOT_FOUND
        ) 