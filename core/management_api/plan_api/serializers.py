from rest_framework import serializers
from core.models import Plan, Feature, PlanFeature


class FeatureSerializer(serializers.ModelSerializer):
    """Serializer für Features"""
    
    class Meta:
        model = Feature
        fields = ['id', 'feature_name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class PlanFeatureSerializer(serializers.ModelSerializer):
    """Serializer für Plan-Feature Zuordnungen"""
    feature = FeatureSerializer(read_only=True)
    feature_name = serializers.CharField(source='feature.feature_name', read_only=True)
    feature_description = serializers.CharField(source='feature.description', read_only=True)
    
    class Meta:
        model = PlanFeature
        fields = ['id', 'feature', 'feature_name', 'feature_description', 'limit', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class PlanSerializer(serializers.ModelSerializer):
    """Serializer für Subscription Pläne"""
    features = PlanFeatureSerializer(many=True, read_only=True, source='planfeature_set')
    feature_count = serializers.SerializerMethodField()
    formatted_price = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    
    class Meta:
        model = Plan
        fields = [
            'id', 'plan_name', 'description', 'price_monthly', 'formatted_price',
            'stripe_product_id', 'stripe_price_id_monthly', 'is_active', 
            'features', 'feature_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_feature_count(self, obj):
        """Anzahl der Features für diesen Plan"""
        return obj.planfeature_set.count()
    
    def get_formatted_price(self, obj):
        """Formatierter Preis mit Währung"""
        if obj.price_monthly:
            return f"{obj.price_monthly}€/Monat"
        return "Individuell (Preis auf Anfrage)"
    
    def get_description(self, obj):
        """Beschreibung basierend auf Plan-Name"""
        descriptions = {
            'Start': 'Ideal für Einzelpersonen und kleine Teams',
            'Pro': 'Am beliebtesten - Ideal für Unternehmen mit höherem Volumen', 
            'Enterprise': 'Individuelle Lösungen für große Unternehmen und Agenturen'
        }
        return descriptions.get(obj.plan_name, 'HotCalls Subscription Plan')


class PlanDetailSerializer(PlanSerializer):
    """Detaillierter Serializer für einzelne Pläne"""
    
    def to_representation(self, instance):
        """Erweiterte Repräsentation mit gruppierten Features"""
        data = super().to_representation(instance)
        
        # Gruppiere Features für bessere Lesbarkeit
        feature_groups = {
            'limits': []
        }
        
        for feature in data['features']:
            feature_name = feature['feature_name']
            limit = feature['limit']
            
            if feature_name == 'call_minutes':
                if limit == 999999:
                    feature_groups['limits'].append({
                        'name': 'Anrufminuten',
                        'value': 'Unbegrenzt',
                        'display': '📞 Unbegrenzte Anrufminuten'
                    })
                else:
                    feature_groups['limits'].append({
                        'name': 'Anrufminuten',
                        'value': f"{limit} Min/Monat",
                        'display': f'📞 {limit} Anrufminuten pro Monat'
                    })
            
            elif feature_name == 'max_users':
                if limit == 999999:
                    feature_groups['limits'].append({
                        'name': 'Benutzer',
                        'value': 'Unbegrenzt',
                        'display': '👥 Unbegrenzte Benutzer'
                    })
                else:
                    feature_groups['limits'].append({
                        'name': 'Benutzer',
                        'value': f"{limit} User",
                        'display': f'👥 {limit} Benutzer erlaubt'
                    })
            
            elif feature_name == 'max_agents':
                if limit == 999999:
                    feature_groups['limits'].append({
                        'name': 'Agents',
                        'value': 'Unbegrenzt',
                        'display': '🤖 Unbegrenzte Agents'
                    })
                else:
                    feature_groups['limits'].append({
                        'name': 'Agents',
                        'value': f"{limit} Agents",
                        'display': f'🤖 {limit} Agents pro Workspace'
                    })
            
            # Overage-Preise und Cosmetic-Flags werden nicht mehr dargestellt
        
        data['feature_groups'] = feature_groups
        return data


class PlanSummarySerializer(serializers.ModelSerializer):
    """Kompakter Serializer für Plan-Übersichten"""
    formatted_price = serializers.SerializerMethodField()
    key_features = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    
    class Meta:
        model = Plan
        fields = ['id', 'plan_name', 'description', 'formatted_price', 'key_features', 'is_active']
    
    def get_formatted_price(self, obj):
        if obj.price_monthly:
            return f"{obj.price_monthly}€/Monat"
        return "Individuell"
    
    def get_description(self, obj):
        """Beschreibung basierend auf Plan-Name"""
        descriptions = {
            'Start': 'Ideal für Einzelpersonen und kleine Teams',
            'Pro': 'Am beliebtesten - Ideal für Unternehmen mit höherem Volumen', 
            'Enterprise': 'Individuelle Lösungen für große Unternehmen und Agenturen'
        }
        return descriptions.get(obj.plan_name, 'HotCalls Subscription Plan')
    
    def get_key_features(self, obj):
        """Wichtigste Features als Liste"""
        features = []
        
        for pf in obj.planfeature_set.all():
            feature_name = pf.feature.feature_name
            limit = pf.limit
            
            if feature_name == 'call_minutes':
                if limit == 999999:
                    features.append("Unbegrenzte Anrufminuten")
                else:
                    features.append(f"{limit} Anrufminuten/Monat")
            
            elif feature_name == 'max_users':
                if limit == 999999:
                    features.append("Unbegrenzte Benutzer")
                else:
                    features.append(f"{limit} Benutzer")
            
            elif feature_name == 'max_agents':
                if limit == 999999:
                    features.append("Unbegrenzte Agents")
                else:
                    features.append(f"{limit} Agents pro Workspace")
            
            # Cosmetic-Flags nicht mehr auflisten
        
        return features 