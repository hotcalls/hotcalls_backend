from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from core.models import Plan, Feature, PlanFeature
from .serializers import (
    PlanSerializer, 
    PlanDetailSerializer, 
    PlanSummarySerializer,
    FeatureSerializer, 
    PlanFeatureSerializer
)
from .permissions import PlanAPIPermissions
from .filters import PlanFilter


class PlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet für Subscription Pläne
    
    Stellt Endpunkte bereit für:
    - Liste aller Pläne
    - Einzelplan-Details
    - Plan-Vergleich
    - Öffentliche Plan-Info
    """
    queryset = Plan.objects.filter(is_active=True).prefetch_related('planfeature_set__feature')
    permission_classes = [AllowAny]  # Pläne sind öffentlich einsehbar
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_class = PlanFilter
    search_fields = ['plan_name', 'description']
    ordering_fields = ['price_monthly', 'plan_name', 'created_at']
    ordering = ['price_monthly']  # Standard: Sortierung nach Preis
    
    def get_serializer_class(self):
        """Wähle Serializer basierend auf Action"""
        if self.action == 'retrieve':
            return PlanDetailSerializer
        elif self.action == 'summary':
            return PlanSummarySerializer
        return PlanSerializer
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Kompakte Übersicht aller Pläne
        GET /api/plans/summary/
        """
        queryset = self.filter_queryset(self.get_queryset())
        serializer = PlanSummarySerializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'plans': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def comparison(self, request):
        """
        Plan-Vergleichstabelle
        GET /api/plans/comparison/
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        comparison_data = []
        all_features = set()
        
        # Sammle alle Features
        for plan in queryset:
            plan_features = {}
            for pf in plan.planfeature_set.all():
                feature_name = pf.feature.feature_name
                all_features.add(feature_name)
                plan_features[feature_name] = {
                    'limit': pf.limit,
                    'description': pf.feature.description
                }
            
            comparison_data.append({
                'plan': PlanSummarySerializer(plan).data,
                'features': plan_features
            })
        
        return Response({
            'comparison': comparison_data,
            'available_features': list(all_features),
            'count': len(comparison_data)
        })
    
    @action(detail=True, methods=['get'])
    def features(self, request, pk=None):
        """
        Alle Features eines Plans
        GET /api/plans/{id}/features/
        """
        plan = self.get_object()
        plan_features = PlanFeature.objects.filter(plan=plan).select_related('feature')
        serializer = PlanFeatureSerializer(plan_features, many=True)
        
        return Response({
            'plan': PlanSummarySerializer(plan).data,
            'features': serializer.data,
            'feature_count': plan_features.count()
        })
    
    @action(detail=False, methods=['get'])
    def pricing(self, request):
        """
        Nur Preisinformationen aller Pläne
        GET /api/plans/pricing/
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        pricing_data = []
        for plan in queryset:
            # Hole Minuten und Überschreitungskosten
            call_minutes = plan.planfeature_set.filter(
                feature__feature_name='call_minutes'
            ).first()
            overage_rate = plan.planfeature_set.filter(
                feature__feature_name='overage_rate_cents'
            ).first()
            
            pricing_data.append({
                'id': plan.id,
                'name': plan.plan_name,
                'monthly_price': plan.price_monthly,
                'formatted_price': f"{plan.price_monthly}€/Monat" if plan.price_monthly else "Individuell",
                'included_minutes': call_minutes.limit if call_minutes else 0,
                'overage_rate_per_minute': (overage_rate.limit / 100) if overage_rate else 0,
                'overage_rate_formatted': f"{overage_rate.limit/100:.2f}€/Min" if overage_rate else "Keine Zusatzkosten"
            })
        
        return Response({
            'pricing': pricing_data,
            'count': len(pricing_data)
        })


class FeatureViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet für Features
    
    Stellt Endpunkte bereit für:
    - Liste aller Features
    - Feature-Details
    """
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['feature_name', 'description']
    ordering_fields = ['feature_name', 'created_at']
    ordering = ['feature_name']
    
    @action(detail=False, methods=['get'])
    def by_plan(self, request):
        """
        Features gruppiert nach Plänen
        GET /api/features/by_plan/
        """
        features_by_plan = {}
        
        for plan in Plan.objects.filter(is_active=True).prefetch_related('planfeature_set__feature'):
            features_by_plan[plan.plan_name] = []
            
            for pf in plan.planfeature_set.all():
                features_by_plan[plan.plan_name].append({
                    'feature': FeatureSerializer(pf.feature).data,
                    'limit': pf.limit,
                    'plan_feature_id': pf.id
                })
        
        return Response(features_by_plan)


class PlanFeatureViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet für Plan-Feature Zuordnungen
    """
    queryset = PlanFeature.objects.select_related('plan', 'feature').all()
    serializer_class = PlanFeatureSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['plan', 'feature']
    ordering_fields = ['plan__plan_name', 'feature__feature_name', 'limit']
    ordering = ['plan__price_monthly', 'feature__feature_name'] 