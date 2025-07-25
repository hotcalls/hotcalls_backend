from rest_framework import serializers
from core.models import Workspace, User


class WorkspaceUserSerializer(serializers.ModelSerializer):
    """Serializer for User model in workspace context"""
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'status']
        read_only_fields = ['id', 'username', 'first_name', 'last_name', 'email', 'status']


class WorkspaceSerializer(serializers.ModelSerializer):
    """Serializer for Workspace model"""
    users = WorkspaceUserSerializer(many=True, read_only=True, source='mapping_user_workspaces')
    user_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Workspace
        fields = [
            'id', 'workspace_name', 'created_at', 'updated_at', 
            'users', 'user_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_count(self, obj):
        """Get the number of users in this workspace"""
        return obj.mapping_user_workspaces.count()


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