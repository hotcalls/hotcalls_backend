from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router für automatische URL-Generierung
router = DefaultRouter()
router.register(r'plans', views.PlanViewSet, basename='plan')
router.register(r'features', views.FeatureViewSet, basename='feature')
router.register(r'plan-features', views.PlanFeatureViewSet, basename='planfeature')

# URL-Patterns
urlpatterns = [
    # Standard Router URLs
    path('', include(router.urls)),
    
    # Zusätzliche custom endpoints könnten hier hinzugefügt werden
    # path('plans/custom-endpoint/', views.custom_view, name='custom-endpoint'),
]

"""
Automatisch generierte URLs durch Router:

PLAN ENDPOINTS:
    GET    /api/plans/                     → Alle Pläne
    GET    /api/plans/{id}/                → Einzelner Plan (Detail)
    GET    /api/plans/summary/             → Kompakte Plan-Übersicht
    GET    /api/plans/comparison/          → Plan-Vergleichstabelle  
    GET    /api/plans/pricing/             → Nur Preisinformationen
    GET    /api/plans/{id}/features/       → Features eines Plans

FEATURE ENDPOINTS:
    GET    /api/features/                  → Alle Features
    GET    /api/features/{id}/             → Einzelnes Feature
    GET    /api/features/by_plan/          → Features gruppiert nach Plänen

PLAN-FEATURE ENDPOINTS:
    GET    /api/plan-features/             → Alle Plan-Feature Zuordnungen
    GET    /api/plan-features/{id}/        → Einzelne Zuordnung

FILTER BEISPIELE:
    GET    /api/plans/?price_max=500                    → Pläne unter 500€
    GET    /api/plans/?has_feature=whitelabel          → Pläne mit Whitelabel
    GET    /api/plans/?min_minutes=500                 → Pläne mit min. 500 Min
    GET    /api/plans/?enterprise_only=true           → Nur Enterprise Pläne
    GET    /api/plans/?affordable_plans=true          → Erschwingliche Pläne
    GET    /api/plans/?ordering=price_monthly         → Sortiert nach Preis
    GET    /api/plans/?search=Pro                     → Suche nach "Pro"
""" 