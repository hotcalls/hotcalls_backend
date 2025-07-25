from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Plan, Feature, PlanFeature


class FeatureSerializer(serializers.ModelSerializer):
    """Serializer for Feature model"""
    
    class Meta:
        model = Feature
        fields = [
            'id', 'feature_name', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PlanFeatureSerializer(serializers.ModelSerializer):
    """Serializer for PlanFeature model"""
    feature_name = serializers.CharField(source='feature.feature_name', read_only=True)
    feature_description = serializers.CharField(source='feature.description', read_only=True)
    plan_name = serializers.CharField(source='plan.plan_name', read_only=True)
    
    class Meta:
        model = PlanFeature
        fields = [
            'id', 'plan', 'plan_name', 'feature', 'feature_name', 
            'feature_description', 'limit', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PlanSerializer(serializers.ModelSerializer):
    """Serializer for Plan model"""
    plan_features = PlanFeatureSerializer(many=True, read_only=True, source='planfeature_set')
    feature_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Plan
        fields = [
            'id', 'plan_name', 'created_at', 'updated_at', 
            'plan_features', 'feature_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.IntegerField)
    def get_feature_count(self, obj) -> int:
        """Get the number of features assigned to this plan"""
        return obj.features.count()


class PlanCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating plans"""
    
    class Meta:
        model = Plan
        fields = ['plan_name']


class PlanFeatureCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating plan-feature assignments"""
    
    class Meta:
        model = PlanFeature
        fields = ['plan', 'feature', 'limit']
    
    def validate(self, data):
        """Validate that the plan-feature combination doesn't already exist"""
        plan = data.get('plan')
        feature = data.get('feature')
        
        if PlanFeature.objects.filter(plan=plan, feature=feature).exists():
            raise serializers.ValidationError(
                "This feature is already assigned to this plan"
            )
        
        return data


class FeatureAvailabilitySerializer(serializers.Serializer):
    """Serializer for checking feature availability for a plan"""
    plan_id = serializers.UUIDField()
    feature_name = serializers.CharField()
    
    def validate_plan_id(self, value):
        """Validate that the plan exists"""
        try:
            Plan.objects.get(id=value)
        except Plan.DoesNotExist:
            raise serializers.ValidationError("Plan does not exist")
        return value 