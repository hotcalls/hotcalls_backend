from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

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
        summary="List all plans",
        description="Retrieve a list of all subscription plans with filtering and search capabilities",
        tags=["Subscription Management"]
    ),
    create=extend_schema(
        summary="Create a new plan",
        description="Create a new subscription plan (staff only)",
        tags=["Subscription Management"]
    ),
    retrieve=extend_schema(
        summary="Get plan details",
        description="Retrieve detailed information about a specific plan including features",
        tags=["Subscription Management"]
    ),
    update=extend_schema(
        summary="Update plan",
        description="Update all fields of a plan (staff only)",
        tags=["Subscription Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update plan",
        description="Update specific fields of a plan (staff only)",
        tags=["Subscription Management"]
    ),
    destroy=extend_schema(
        summary="Delete plan",
        description="Delete a subscription plan (superuser only)",
        tags=["Subscription Management"]
    ),
)
class PlanViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Plan model operations
    
    Provides CRUD operations for subscription plans:
    - All users can view plans
    - Staff can create/modify plans
    - Superusers can delete plans
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
        summary="Get plan features",
        description="Get all features assigned to a specific plan",
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
        summary="Add feature to plan",
        description="Assign a feature to a plan with a specific limit (staff only)",
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
        summary="Remove feature from plan",
        description="Remove a feature assignment from a plan (staff only)",
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
        summary="List all features",
        description="Retrieve a list of all available features with filtering and search capabilities",
        tags=["Subscription Management"]
    ),
    create=extend_schema(
        summary="Create a new feature",
        description="Create a new feature (staff only)",
        tags=["Subscription Management"]
    ),
    retrieve=extend_schema(
        summary="Get feature details",
        description="Retrieve detailed information about a specific feature",
        tags=["Subscription Management"]
    ),
    update=extend_schema(
        summary="Update feature",
        description="Update all fields of a feature (staff only)",
        tags=["Subscription Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update feature",
        description="Update specific fields of a feature (staff only)",
        tags=["Subscription Management"]
    ),
    destroy=extend_schema(
        summary="Delete feature",
        description="Delete a feature (superuser only)",
        tags=["Subscription Management"]
    ),
)
class FeatureViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Feature model operations
    
    Provides CRUD operations for features:
    - All users can view features
    - Staff can create/modify features
    - Superusers can delete features
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
        summary="Get feature plans",
        description="Get all plans that include this feature",
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
        summary="List plan-feature assignments",
        description="Retrieve a list of all plan-feature assignments with filtering capabilities",
        tags=["Subscription Management"]
    ),
    create=extend_schema(
        summary="Create plan-feature assignment",
        description="Assign a feature to a plan with a specific limit (staff only)",
        tags=["Subscription Management"]
    ),
    retrieve=extend_schema(
        summary="Get assignment details",
        description="Retrieve detailed information about a specific plan-feature assignment",
        tags=["Subscription Management"]
    ),
    update=extend_schema(
        summary="Update assignment",
        description="Update a plan-feature assignment (staff only)",
        tags=["Subscription Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update assignment",
        description="Update specific fields of a plan-feature assignment (staff only)",
        tags=["Subscription Management"]
    ),
    destroy=extend_schema(
        summary="Delete assignment",
        description="Remove a feature from a plan (staff only)",
        tags=["Subscription Management"]
    ),
)
class PlanFeatureViewSet(viewsets.ModelViewSet):
    """
    ViewSet for PlanFeature model operations
    
    Provides CRUD operations for plan-feature assignments:
    - All users can view assignments
    - Staff can create/modify/delete assignments
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