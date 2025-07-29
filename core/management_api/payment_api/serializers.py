from rest_framework import serializers
from core.models import Workspace


class StripeCustomerSerializer(serializers.ModelSerializer):
    """Serializer for Stripe customer operations"""
    has_stripe_customer = serializers.SerializerMethodField()
    
    class Meta:
        model = Workspace
        fields = ['id', 'workspace_name', 'stripe_customer_id', 'has_stripe_customer']
        read_only_fields = ['id', 'workspace_name', 'stripe_customer_id', 'has_stripe_customer']
    
    def get_has_stripe_customer(self, obj):
        """Check if workspace has a Stripe customer ID"""
        return bool(obj.stripe_customer_id)


class CreateStripeCustomerSerializer(serializers.Serializer):
    """Serializer for creating a Stripe customer"""
    workspace_id = serializers.UUIDField()
    email = serializers.EmailField(required=False)
    name = serializers.CharField(max_length=255, required=False)
    
    def validate_workspace_id(self, value):
        """Validate that workspace exists and user has access"""
        try:
            workspace = Workspace.objects.get(id=value)
            
            # Check if user is member of workspace
            request = self.context.get('request')
            if request and not workspace.users.filter(id=request.user.id).exists():
                raise serializers.ValidationError("You don't have access to this workspace")
                
            return value
        except Workspace.DoesNotExist:
            raise serializers.ValidationError("Workspace does not exist")


class StripePortalSessionSerializer(serializers.Serializer):
    """Serializer for creating Stripe customer portal session"""
    workspace_id = serializers.UUIDField()
    return_url = serializers.URLField(required=False)
    
    def validate_workspace_id(self, value):
        """Validate workspace and check for Stripe customer"""
        try:
            workspace = Workspace.objects.get(id=value)
            
            # Check if user is member of workspace
            request = self.context.get('request')
            if request and not workspace.users.filter(id=request.user.id).exists():
                raise serializers.ValidationError("You don't have access to this workspace")
            
            # Check if workspace has Stripe customer
            if not workspace.stripe_customer_id:
                raise serializers.ValidationError("This workspace doesn't have a Stripe customer yet")
                
            return value
        except Workspace.DoesNotExist:
            raise serializers.ValidationError("Workspace does not exist")


class RetrieveStripeCustomerSerializer(serializers.Serializer):
    """Serializer for retrieving Stripe customer details"""
    workspace_id = serializers.UUIDField()
    
    def validate_workspace_id(self, value):
        """Validate workspace access"""
        try:
            workspace = Workspace.objects.get(id=value)
            
            # Check if user is member of workspace
            request = self.context.get('request')
            if request and not workspace.users.filter(id=request.user.id).exists():
                raise serializers.ValidationError("You don't have access to this workspace")
                
            return value
        except Workspace.DoesNotExist:
            raise serializers.ValidationError("Workspace does not exist") 


class CreateCheckoutSessionSerializer(serializers.Serializer):
    """Serializer for creating Stripe checkout session"""
    workspace_id = serializers.UUIDField()
    price_id = serializers.CharField(
        max_length=255,
        help_text="Stripe Price ID (price_xxx)"
    )
    success_url = serializers.URLField(
        help_text="URL to redirect after successful payment"
    )
    cancel_url = serializers.URLField(
        help_text="URL to redirect if payment is cancelled"
    )
    
    def validate_workspace_id(self, value):
        """Validate workspace exists and user has access"""
        try:
            workspace = Workspace.objects.get(id=value)
            
            # Check if user is member of workspace
            request = self.context.get('request')
            if request and not workspace.users.filter(id=request.user.id).exists():
                raise serializers.ValidationError("You don't have access to this workspace")
            
            # Check if workspace already has a Stripe customer
            if not workspace.stripe_customer_id:
                raise serializers.ValidationError("Workspace needs a Stripe customer first")
                
            return value
        except Workspace.DoesNotExist:
            raise serializers.ValidationError("Workspace does not exist") 