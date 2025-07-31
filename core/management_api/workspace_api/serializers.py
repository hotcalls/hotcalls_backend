from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Workspace, User


class WorkspaceUserSerializer(serializers.ModelSerializer):
    """Serializer for User model in workspace context"""
    
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'status']
        read_only_fields = ['id', 'email', 'first_name', 'last_name', 'status']


class WorkspaceSerializer(serializers.ModelSerializer):
    """Serializer for Workspace model"""
    users = WorkspaceUserSerializer(many=True, read_only=True)
    user_count = serializers.SerializerMethodField()
    is_subscription_active = serializers.SerializerMethodField()
    
    class Meta:
        model = Workspace
        fields = [
            'id', 'workspace_name', 'created_at', 'updated_at', 
            'users', 'user_count', 'is_subscription_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.IntegerField)
    def get_user_count(self, obj) -> int:
        """Get the number of users in this workspace"""
        return obj.users.count()
    
    @extend_schema_field(serializers.BooleanField)
    def get_is_subscription_active(self, obj) -> bool:
        """Determine if the subscription is currently active based on Stripe data"""
        # TODO: Check Stripe subscription status here
        # For now return True if stripe_subscription_id exists
        return bool(obj.stripe_subscription_id)


class WorkspaceCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating workspaces"""
    
    class Meta:
        model = Workspace
        fields = ['workspace_name']


class WorkspaceUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating workspaces"""
    
    class Meta:
        model = Workspace
        fields = ['workspace_name']


class WorkspaceUserAssignmentSerializer(serializers.Serializer):
    """Serializer for adding/removing users from workspace"""
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="List of user IDs to add/remove"
    )
    
    def validate_user_ids(self, value):
        """Validate that all user IDs exist"""
        existing_users = User.objects.filter(id__in=value)
        if len(existing_users) != len(value):
            missing_ids = set(value) - set(existing_users.values_list('id', flat=True))
            raise serializers.ValidationError(
                f"The following user IDs do not exist: {list(missing_ids)}"
            )
        return value


class WorkspaceStatsSerializer(serializers.Serializer):
    """Serializer for workspace statistics"""
    workspace_id = serializers.UUIDField(read_only=True)
    workspace_name = serializers.CharField(read_only=True)
    user_count = serializers.IntegerField(read_only=True)
    agent_count = serializers.IntegerField(read_only=True)
    calendar_count = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True) 