from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample

from core.models import Plan, Feature, PlanFeature
from .serializers import (
    PlanSerializer, PlanCreateSerializer, FeatureSerializer,
    PlanFeatureSerializer, PlanFeatureCreateSerializer,
    FeatureAvailabilitySerializer
)
from .filters import PlanFilter, FeatureFilter, PlanFeatureFilter
from .permissions import SubscriptionPermission, PlanFeaturePermission


@extend_schema_view(
    list=extend_schema(
        summary="📋 List all subscription plans",
        description="""
        Retrieve all available subscription plans with their features.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can view all subscription plans
        - **✅ Staff/Superuser**: Same access level as regular users
        
        **📊 Public Information**:
        - Plan names and descriptions
        - Associated features and limits
        - Pricing and availability information
        
        **🎯 Use Cases**:
        - Plan selection UI
        - Feature comparison
        - Subscription management
        """,
        responses={
            200: OpenApiResponse(
                response=PlanSerializer(many=True),
                description="✅ Successfully retrieved all subscription plans",
                examples=[
                    OpenApiExample(
                        'Plans List',
                        summary='Available subscription plans',
                        value={
                            'count': 3,
                            'results': [
                                {
                                    'id': 'plan-uuid-1',
                                    'plan_name': 'Basic Plan',
                                    'feature_count': 5,
                                    'plan_features': [
                                        {'feature_name': 'Call Tracking', 'limit': 100},
                                        {'feature_name': 'Agents', 'limit': 2}
                                    ]
                                },
                                {
                                    'id': 'plan-uuid-2', 
                                    'plan_name': 'Pro Plan',
                                    'feature_count': 10,
                                    'plan_features': [
                                        {'feature_name': 'Call Tracking', 'limit': 1000},
                                        {'feature_name': 'Agents', 'limit': 10}
                                    ]
                                }
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to view plans")
        },
        tags=["Subscription Management"]
    ),
    create=extend_schema(
        summary="➕ Create new subscription plan",
        description="""
        Create a new subscription plan for the system.
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot create plans
        - **✅ Staff Members**: Can create new subscription plans
        - **✅ Superusers**: Can create new subscription plans
        
        **💼 Business Operation**:
        - Defines available service tiers
        - Sets up feature boundaries
        - Establishes billing structures
        
        **📝 Required Information**:
        - `plan_name`: Unique plan identifier
        - Features can be added separately via plan-feature endpoints
        """,
        request=PlanCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=PlanSerializer,
                description="✅ Subscription plan created successfully",
                examples=[
                    OpenApiExample(
                        'New Plan Created',
                        summary='Successfully created plan',
                        value={
                            'id': 'new-plan-uuid',
                            'plan_name': 'Enterprise Plan',
                            'feature_count': 0,
                            'plan_features': [],
                            'created_at': '2024-01-15T10:30:00Z'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error - Plan name may already exist"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(
                description="🚫 Permission denied - Staff access required for plan creation",
                examples=[
                    OpenApiExample(
                        'Access Denied',
                        summary='Regular user attempted plan creation',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            )
        },
        tags=["Subscription Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get subscription plan details",
        description="""
        Retrieve detailed information about a specific subscription plan.
        
        **🔐 Permission Requirements**: All authenticated users can view plan details
        
        **📊 Detailed Information**:
        - Complete plan configuration
        - All associated features with limits
        - Feature count and availability
        """,
        responses={
            200: OpenApiResponse(response=PlanSerializer, description="✅ Plan details retrieved successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Subscription plan not found")
        },
        tags=["Subscription Management"]
    ),
    update=extend_schema(
        summary="✏️ Update subscription plan",
        description="""
        Update subscription plan information (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot modify plans
        - **✅ Staff Members**: Can update plan details
        - **✅ Superusers**: Can update plan details
        
        **⚠️ Business Impact**:
        - May affect existing subscribers
        - Consider versioning for major changes
        - Communicate changes to users
        """,
        request=PlanCreateSerializer,
        responses={
            200: OpenApiResponse(response=PlanSerializer, description="✅ Plan updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Plan not found")
        },
        tags=["Subscription Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update subscription plan",
        description="""
        Update specific fields of a subscription plan (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        """,
        request=PlanCreateSerializer,
        responses={
            200: OpenApiResponse(response=PlanSerializer, description="✅ Plan updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Plan not found")
        },
        tags=["Subscription Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete subscription plan",
        description="""
        **⚠️ DESTRUCTIVE OPERATION - Permanently delete a subscription plan.**
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: No access to plan deletion
        - **❌ Staff Members**: Cannot delete plans
        - **✅ Superuser ONLY**: Can delete subscription plans
        
        **💥 Critical Considerations**:
        - May affect existing subscribers
        - All plan-feature relationships will be removed
        - Cannot be undone - consider deactivation instead
        
        **🛡️ Safety Recommendations**:
        - Ensure no active subscriptions use this plan
        - Backup plan configuration before deletion
        - Consider plan archival instead of deletion
        """,
        responses={
            204: OpenApiResponse(description="✅ Plan deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(
                description="🚫 Permission denied - Only superusers can delete plans",
                examples=[
                    OpenApiExample(
                        'Insufficient Permissions',
                        summary='Non-superuser attempted plan deletion',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            ),
            404: OpenApiResponse(description="🚫 Plan not found")
        },
        tags=["Subscription Management"]
    ),
)
class PlanViewSet(viewsets.ModelViewSet):
    """
    📋 **Subscription Plan Management with Role-Based Access**
    
    Manages subscription plans with different access levels:
    - **👤 All Users**: Can view plans and features (public information)
    - **👔 Staff**: Can create and modify plans
    - **🔧 Superusers**: Can delete plans (destructive operations)
    """
    queryset = Plan.objects.all()
    permission_classes = [SubscriptionPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PlanFilter
    search_fields = ['plan_name']
    ordering_fields = ['plan_name', 'created_at', 'updated_at']
    ordering = ['plan_name']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return PlanCreateSerializer
        return PlanSerializer
    
    @extend_schema(
        summary="📋 Get plan features",
        description="""
        Get all features assigned to a specific subscription plan.
        
        **🔐 Permission Requirements**: All authenticated users can access
        
        **📊 Response Details**:
        - All features included in the plan
        - Feature limits and configurations
        - Plan-specific feature settings
        """,
        responses={
            200: OpenApiResponse(
                response=PlanFeatureSerializer(many=True),
                description="✅ Plan features retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Plan not found")
        },
        tags=["Subscription Management"]
    )
    @action(detail=True, methods=['get'])
    def features(self, request, pk=None):
        """Get all features for a specific plan"""
        plan = self.get_object()
        plan_features = PlanFeature.objects.filter(plan=plan)
        serializer = PlanFeatureSerializer(plan_features, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="➕ Add feature to plan",
        description="""
        Assign a feature to a subscription plan with specific limits.
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot modify plan features
        - **✅ Staff Members**: Can assign features to plans
        - **✅ Superusers**: Can assign features to plans
        
        **📝 Required Information**:
        - `feature`: Feature ID to assign
        - `limit`: Usage limit for this feature in this plan
        
        **💡 Business Logic**:
        - Creates plan-feature relationship
        - Sets feature-specific limits
        - Enables feature for plan subscribers
        """,
        request=PlanFeatureCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=PlanFeatureSerializer,
                description="✅ Feature assigned to plan successfully"
            ),
            400: OpenApiResponse(description="❌ Validation error - Feature may already be assigned"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Plan not found")
        },
        tags=["Subscription Management"]
    )
    @action(detail=True, methods=['post'], permission_classes=[SubscriptionPermission])
    def add_feature(self, request, pk=None):
        """Add a feature to a plan"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can modify plan features'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        plan = self.get_object()
        data = request.data.copy()
        data['plan'] = plan.id
        
        serializer = PlanFeatureCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="➖ Remove feature from plan",
        description="""
        Remove a feature assignment from a subscription plan.
        
        **🔐 Permission Requirements**: Staff access required
        
        **📝 Required Information**:
        - `feature_id`: ID of feature to remove from plan
        
        **⚠️ Impact**:
        - Removes feature access for plan subscribers
        - May affect existing user capabilities
        - Consider migration path for affected users
        """,
        request={'type': 'object', 'properties': {'feature_id': {'type': 'string', 'format': 'uuid'}}},
        responses={
            204: OpenApiResponse(description="✅ Feature removed from plan successfully"),
            400: OpenApiResponse(description="❌ feature_id is required"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Feature not found in this plan")
        },
        tags=["Subscription Management"]
    )
    @action(detail=True, methods=['delete'], permission_classes=[SubscriptionPermission])
    def remove_feature(self, request, pk=None):
        """Remove a feature from a plan"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can modify plan features'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        plan = self.get_object()
        feature_id = request.data.get('feature_id')
        
        if not feature_id:
            return Response(
                {'error': 'feature_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            plan_feature = PlanFeature.objects.get(plan=plan, feature_id=feature_id)
            plan_feature.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except PlanFeature.DoesNotExist:
            return Response(
                {'error': 'Feature not found in this plan'}, 
                status=status.HTTP_404_NOT_FOUND
            )


@extend_schema_view(
    list=extend_schema(
        summary="🔧 List all features",
        description="""
        Retrieve all available features that can be assigned to plans.
        
        **🔐 Permission Requirements**: All authenticated users can view features
        
        **📊 Feature Information**:
        - Feature names and descriptions
        - Available capabilities
        - Feature metadata and configuration options
        """,
        responses={
            200: OpenApiResponse(response=FeatureSerializer(many=True), description="✅ Features retrieved successfully"),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Subscription Management"]
    ),
    create=extend_schema(
        summary="➕ Create new feature",
        description="""
        Create a new feature that can be assigned to subscription plans.
        
        **🔐 Permission Requirements**: Staff access required
        
        **📝 Feature Definition**:
        - `feature_name`: Unique feature identifier
        - `description`: Feature capabilities and benefits
        """,
        request=FeatureSerializer,
        responses={
            201: OpenApiResponse(response=FeatureSerializer, description="✅ Feature created successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required")
        },
        tags=["Subscription Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get feature details",
        description="""Get detailed information about a specific feature.""",
        responses={
            200: OpenApiResponse(response=FeatureSerializer, description="✅ Feature details retrieved"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Feature not found")
        },
        tags=["Subscription Management"]
    ),
    update=extend_schema(
        summary="✏️ Update feature",
        description="""Update feature information (Staff only).""",
        request=FeatureSerializer,
        responses={
            200: OpenApiResponse(response=FeatureSerializer, description="✅ Feature updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Feature not found")
        },
        tags=["Subscription Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update feature",
        description="""Update specific fields of a feature (Staff only).""",
        request=FeatureSerializer,
        responses={
            200: OpenApiResponse(response=FeatureSerializer, description="✅ Feature updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Feature not found")
        },
        tags=["Subscription Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete feature",
        description="""
        **⚠️ DESTRUCTIVE OPERATION - Permanently delete a feature.**
        
        **🔐 Permission Requirements**: Superuser only
        
        **💥 Impact**: Removes feature from all plans and affects all subscribers
        """,
        responses={
            204: OpenApiResponse(description="✅ Feature deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Superuser access required"),
            404: OpenApiResponse(description="🚫 Feature not found")
        },
        tags=["Subscription Management"]
    ),
)
class FeatureViewSet(viewsets.ModelViewSet):
    """
    🔧 **Feature Management with Role-Based Access**
    
    Manages system features with appropriate permission levels:
    - **👤 All Users**: Can view available features
    - **👔 Staff**: Can create and modify features  
    - **🔧 Superusers**: Can delete features
    """
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer
    permission_classes = [SubscriptionPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = FeatureFilter
    search_fields = ['feature_name', 'description']
    ordering_fields = ['feature_name', 'created_at', 'updated_at']
    ordering = ['feature_name']
    
    @extend_schema(
        summary="📋 Get feature plans",
        description="""
        Get all subscription plans that include this feature.
        
        **🔐 Permission Requirements**: All authenticated users
        """,
        responses={
            200: OpenApiResponse(response=PlanFeatureSerializer(many=True), description="✅ Feature plans retrieved"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Feature not found")
        },
        tags=["Subscription Management"]
    )
    @action(detail=True, methods=['get'])
    def plans(self, request, pk=None):
        """Get all plans that include this feature"""
        feature = self.get_object()
        plan_features = PlanFeature.objects.filter(feature=feature)
        serializer = PlanFeatureSerializer(plan_features, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary="🔗 List plan-feature assignments",
        description="""
        Retrieve all plan-feature assignments showing which features are included in which plans.
        
        **🔐 Permission Requirements**: All authenticated users can view assignments
        """,
        responses={
            200: OpenApiResponse(response=PlanFeatureSerializer(many=True), description="✅ Assignments retrieved"),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Subscription Management"]
    ),
    create=extend_schema(
        summary="➕ Create plan-feature assignment",
        description="""
        Assign a feature to a plan with specific limits (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        """,
        request=PlanFeatureCreateSerializer,
        responses={
            201: OpenApiResponse(response=PlanFeatureSerializer, description="✅ Assignment created successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied")
        },
        tags=["Subscription Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get assignment details",
        description="""Get detailed information about a plan-feature assignment.""",
        responses={
            200: OpenApiResponse(response=PlanFeatureSerializer, description="✅ Assignment details retrieved"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Assignment not found")
        },
        tags=["Subscription Management"]
    ),
    update=extend_schema(
        summary="✏️ Update assignment",
        description="""Update a plan-feature assignment (Staff only).""",
        request=PlanFeatureSerializer,
        responses={
            200: OpenApiResponse(response=PlanFeatureSerializer, description="✅ Assignment updated"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Assignment not found")
        },
        tags=["Subscription Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update assignment",
        description="""Update specific fields of a plan-feature assignment (Staff only).""",
        request=PlanFeatureSerializer,
        responses={
            200: OpenApiResponse(response=PlanFeatureSerializer, description="✅ Assignment updated"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Assignment not found")
        },
        tags=["Subscription Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete assignment",
        description="""Remove a feature from a plan (Staff only).""",
        responses={
            204: OpenApiResponse(description="✅ Assignment deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Assignment not found")
        },
        tags=["Subscription Management"]
    ),
)
class PlanFeatureViewSet(viewsets.ModelViewSet):
    """
    🔗 **Plan-Feature Assignment Management**
    
    Manages the relationship between plans and features:
    - **👤 All Users**: Can view assignments
    - **👔 Staff**: Can create/modify/delete assignments
    """
    queryset = PlanFeature.objects.all()
    permission_classes = [PlanFeaturePermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PlanFeatureFilter
    search_fields = ['plan__plan_name', 'feature__feature_name']
    ordering_fields = ['created_at', 'updated_at', 'limit']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return PlanFeatureCreateSerializer
        return PlanFeatureSerializer 