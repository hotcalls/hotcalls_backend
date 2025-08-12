from rest_framework import serializers
from core.models import LeadFunnel, Agent, MetaLeadForm, Workspace
from core.management_api.agent_api.serializers import AgentBasicSerializer
from core.management_api.meta_api.serializers import MetaLeadFormSerializer


class LeadFunnelSerializer(serializers.ModelSerializer):
    """Serializer for LeadFunnel with detailed information"""
    agent = AgentBasicSerializer(read_only=True)
    meta_lead_form = MetaLeadFormSerializer(read_only=True)
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    has_agent = serializers.BooleanField(read_only=True)
    lead_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = LeadFunnel
        fields = [
            'id', 'name', 'workspace', 'workspace_name',
            'meta_lead_form', 'agent', 'has_agent',
            'is_active', 'lead_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'has_agent', 'lead_count']
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        # Simple safe has_agent calculation
        try:
            data['has_agent'] = bool(getattr(instance, 'agent', None))
        except Exception:
            data['has_agent'] = False
            
        return data


class LeadFunnelCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a LeadFunnel"""
    meta_lead_form_id = serializers.UUIDField(write_only=True, required=False)
    
    class Meta:
        model = LeadFunnel
        fields = ['name', 'workspace', 'meta_lead_form_id', 'is_active']
    
    def validate(self, attrs):
        """Validate funnel creation"""
        user = self.context['request'].user
        workspace = attrs.get('workspace')
        
        # Verify user has access to workspace
        if workspace not in user.mapping_user_workspaces.all():
            raise serializers.ValidationError("You don't have access to this workspace")
        
        # If meta_lead_form_id provided, validate it
        if 'meta_lead_form_id' in attrs:
            meta_form_id = attrs.pop('meta_lead_form_id')
            try:
                meta_form = MetaLeadForm.objects.get(id=meta_form_id)
                
                # Check if form already has a funnel
                if hasattr(meta_form, 'lead_funnel'):
                    raise serializers.ValidationError(
                        f"Meta form {meta_form.name} already has a funnel"
                    )
                
                # Check workspace match
                if meta_form.meta_integration.workspace != workspace:
                    raise serializers.ValidationError(
                        "Meta form must be in the same workspace as the funnel"
                    )
                
                attrs['meta_lead_form'] = meta_form
            except MetaLeadForm.DoesNotExist:
                raise serializers.ValidationError("Meta lead form not found")
        
        return attrs


class LeadFunnelUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a LeadFunnel"""
    
    class Meta:
        model = LeadFunnel
        fields = ['name', 'is_active']
    
    def validate(self, attrs):
        """Validate funnel update"""
        user = self.context['request'].user
        funnel = self.instance
        
        # Verify user has access to workspace
        if funnel.workspace not in user.mapping_user_workspaces.all():
            raise serializers.ValidationError("You don't have access to this funnel")
        
        return attrs


class AssignAgentSerializer(serializers.Serializer):
    """Serializer for assigning an agent to a funnel"""
    agent_id = serializers.UUIDField()
    
    def validate_agent_id(self, value):
        """Validate agent assignment"""
        user = self.context['request'].user
        funnel = self.context['funnel']
        
        try:
            agent = Agent.objects.get(agent_id=value)
            
            # Check workspace match
            if agent.workspace != funnel.workspace:
                raise serializers.ValidationError(
                    "Agent must be in the same workspace as the funnel"
                )
            
            # Check if agent is already assigned to another funnel
            if agent.lead_funnel and agent.lead_funnel != funnel:
                raise serializers.ValidationError(
                    f"Agent {agent.name} is already assigned to another funnel"
                )
            
            # Check if agent is active
            if agent.status != 'active':
                raise serializers.ValidationError(
                    f"Agent {agent.name} is not active"
                )
            
            return agent
            
        except Agent.DoesNotExist:
            raise serializers.ValidationError("Agent not found")


class UnassignAgentSerializer(serializers.Serializer):
    """Serializer for unassigning an agent from a funnel"""
    confirm = serializers.BooleanField(
        required=True,
        help_text="Confirm that you want to unassign the agent"
    )
    
    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("You must confirm the unassignment")
        return value 