import stripe
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework.permissions import IsAuthenticated

from core.models import Workspace
from .serializers import (
    StripeCustomerSerializer,
    CreateStripeCustomerSerializer,
    StripePortalSessionSerializer,
    RetrieveStripeCustomerSerializer
)
from .permissions import IsWorkspaceMember


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
@permission_classes([IsAuthenticated])
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
    summary="🔔 Stripe webhook endpoint",
    description="""
    Receive and process Stripe webhook events.
    
    **🔐 Security**:
    - Validates webhook signature
    - No authentication required (Stripe sends directly)
    
    **📊 Handled Events**:
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
    
    # Subscription events (for future use with usage-based billing)
    elif event_type == 'customer.subscription.created':
        subscription = event_data
        customer_id = subscription['customer']
        print(f"Subscription created for customer {customer_id}")
    
    elif event_type == 'customer.subscription.updated':
        subscription = event_data
        customer_id = subscription['customer']
        print(f"Subscription updated for customer {customer_id}")
    
    elif event_type == 'customer.subscription.deleted':
        subscription = event_data
        customer_id = subscription['customer']
        print(f"Subscription cancelled for customer {customer_id}")
    
    else:
        # Unhandled event type
        print(f"Unhandled event type: {event_type}")
    
    # Return success response
    return Response({"received": True}, status=status.HTTP_200_OK) 