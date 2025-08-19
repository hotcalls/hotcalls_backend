from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Workspace, User, WorkspaceInvitation
from core.utils.crypto import encrypt_text, decrypt_text


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
    admin_user_id = serializers.SerializerMethodField()
    creator_id = serializers.SerializerMethodField()
    
    class Meta:
        model = Workspace
        fields = [
            'id', 'workspace_name', 'created_at', 'updated_at', 
            'users', 'user_count', 'is_subscription_active',
            'admin_user_id', 'creator_id',
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

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_admin_user_id(self, obj):
        try:
            return getattr(obj.admin_user, 'id', None)
        except Exception:
            return None

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_creator_id(self, obj):
        try:
            return getattr(obj.creator, 'id', None)
        except Exception:
            return None


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


class WorkspaceSmtpSettingsSerializer(serializers.Serializer):
    """Serializer for per-workspace SMTP configuration (password write-only)."""
    smtp_enabled = serializers.BooleanField(required=True)
    smtp_host = serializers.CharField(required=False, allow_blank=True, default='')
    smtp_port = serializers.IntegerField(required=False, default=587)
    smtp_use_tls = serializers.BooleanField(required=False, default=True)
    smtp_use_ssl = serializers.BooleanField(required=False, default=False)
    smtp_username = serializers.CharField(required=False, allow_blank=True, default='')
    smtp_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    smtp_from_email = serializers.EmailField(required=False, allow_blank=True, default='')

    def to_representation(self, instance: Workspace):
        return {
            'smtp_enabled': instance.smtp_enabled,
            'smtp_host': instance.smtp_host,
            'smtp_port': instance.smtp_port,
            'smtp_use_tls': instance.smtp_use_tls,
            'smtp_use_ssl': instance.smtp_use_ssl,
            'smtp_username': instance.smtp_username,
            'smtp_from_email': instance.smtp_from_email,
            # Never expose password; indicate whether it's set
            'smtp_password_set': bool(instance.smtp_password_encrypted),
        }

    def update_instance(self, workspace: Workspace, data: dict) -> Workspace:
        workspace.smtp_enabled = data.get('smtp_enabled', workspace.smtp_enabled)
        workspace.smtp_host = data.get('smtp_host', workspace.smtp_host)
        workspace.smtp_port = data.get('smtp_port', workspace.smtp_port)
        workspace.smtp_use_tls = data.get('smtp_use_tls', workspace.smtp_use_tls)
        workspace.smtp_use_ssl = data.get('smtp_use_ssl', workspace.smtp_use_ssl)
        workspace.smtp_username = data.get('smtp_username', workspace.smtp_username)
        workspace.smtp_from_email = data.get('smtp_from_email', workspace.smtp_from_email)
        pwd = data.get('smtp_password')
        if pwd is not None:
            workspace.smtp_password_encrypted = encrypt_text(pwd) if pwd else ''
        workspace.save()
        return workspace


class WorkspaceSmtpTestSerializer(serializers.Serializer):
    to_email = serializers.EmailField()


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


class WorkspaceInvitationSerializer(serializers.ModelSerializer):
    """Serializer for WorkspaceInvitation model"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    invited_by_name = serializers.CharField(source='invited_by.get_full_name', read_only=True)
    invited_by_email = serializers.CharField(source='invited_by.email', read_only=True)
    is_valid = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkspaceInvitation
        fields = [
            'id', 'email', 'status', 'created_at', 'expires_at', 'accepted_at',
            'workspace_name', 'invited_by_name', 'invited_by_email', 'is_valid'
        ]
        read_only_fields = [
            'id', 'status', 'created_at', 'expires_at', 'accepted_at',
            'workspace_name', 'invited_by_name', 'invited_by_email', 'is_valid'
        ]
    
    @extend_schema_field(serializers.BooleanField)
    def get_is_valid(self, obj) -> bool:
        """Check if invitation is still valid"""
        return obj.is_valid()


class WorkspaceInviteUserSerializer(serializers.Serializer):
    """Serializer for inviting users to workspace"""
    email = serializers.EmailField(
        help_text="Email address of the user to invite"
    )
    
    def validate_email(self, value):
        """Custom validation for email"""
        # Normalize email to lowercase
        value = value.lower()
        
        # Get workspace from context
        workspace = self.context.get('workspace')
        if not workspace:
            raise serializers.ValidationError("Workspace context is required")
        
        # Check if user is already a member of the workspace
        try:
            user = User.objects.get(email=value)
            if user in workspace.users.all():
                raise serializers.ValidationError(
                    "This user is already a member of the workspace"
                )
        except User.DoesNotExist:
            # User doesn't exist yet - that's fine for invitations
            pass
        
        # Check if there's already a pending invitation
        existing_invitation = WorkspaceInvitation.objects.filter(
            workspace=workspace,
            email=value,
            status='pending'
        ).first()
        
        if existing_invitation and existing_invitation.is_valid():
            raise serializers.ValidationError(
                "A pending invitation already exists for this email address"
            )
        
        return value


class WorkspaceInviteBulkSerializer(serializers.Serializer):
    """Serializer for bulk inviting users to workspace"""
    emails = serializers.ListField(
        child=serializers.EmailField(),
        help_text="List of email addresses to invite",
        min_length=1,
        max_length=50  # Limit bulk invitations
    )
    
    def validate_emails(self, value):
        """Custom validation for bulk emails"""
        # Normalize emails to lowercase and remove duplicates
        normalized_emails = list(set(email.lower() for email in value))
        
        # Get workspace from context
        workspace = self.context.get('workspace')
        if not workspace:
            raise serializers.ValidationError("Workspace context is required")
        
        # Check each email
        errors = {}
        valid_emails = []
        
        for email in normalized_emails:
            try:
                # Check if user is already a member
                try:
                    user = User.objects.get(email=email)
                    if user in workspace.users.all():
                        errors[email] = "Already a member of this workspace"
                        continue
                except User.DoesNotExist:
                    pass  # User doesn't exist - that's fine
                
                # Check for existing pending invitation
                existing_invitation = WorkspaceInvitation.objects.filter(
                    workspace=workspace,
                    email=email,
                    status='pending'
                ).first()
                
                if existing_invitation and existing_invitation.is_valid():
                    errors[email] = "Pending invitation already exists"
                    continue
                
                valid_emails.append(email)
                
            except Exception as e:
                errors[email] = str(e)
        
        if errors:
            raise serializers.ValidationError({
                'invalid_emails': errors,
                'valid_emails': valid_emails
            })
        
        return valid_emails


class InvitationDetailSerializer(serializers.ModelSerializer):
    """Serializer for public invitation details (before acceptance)"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    invited_by_name = serializers.CharField(source='invited_by.get_full_name', read_only=True)
    is_valid = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkspaceInvitation
        fields = [
            'email', 'workspace_name', 'invited_by_name', 
            'created_at', 'expires_at', 'is_valid'
        ]
        read_only_fields = ['email', 'workspace_name', 'invited_by_name', 'created_at', 'expires_at', 'is_valid']
    
    @extend_schema_field(serializers.BooleanField)
    def get_is_valid(self, obj) -> bool:
        """Check if invitation is still valid"""
        return obj.is_valid() 