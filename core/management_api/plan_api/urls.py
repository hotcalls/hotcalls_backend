from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router für automatische URL-Generierung
router = DefaultRouter()
router.register(r'', views.PlanViewSet, basename='plan')  # Empty string to avoid /plans/plans/
router.register(r'features', views.FeatureViewSet, basename='feature')
router.register(r'plan-features', views.PlanFeatureViewSet, basename='planfeature')

# URL-Patterns
urlpatterns = [
    # Standard Router URLs
    path('', include(router.urls)),
    
    # Zusätzliche custom endpoints könnten hier hinzugefügt werden
    # path('custom-endpoint/', views.custom_view, name='custom-endpoint'),
]

"""
Automatisch generierte URLs durch Router:

PLAN ENDPOINTS:
    GET    /api/plans/                     → Alle Pläne
    POST   /api/plans/                     → Plan erstellen
    GET    /api/plans/{id}/                → Einzelner Plan (Detail)
    PUT    /api/plans/{id}/                → Plan vollständig bearbeiten
    PATCH  /api/plans/{id}/                → Plan teilweise bearbeiten
    DELETE /api/plans/{id}/                → Plan löschen
    GET    /api/plans/summary/             → Kompakte Plan-Übersicht
    GET    /api/plans/comparison/          → Plan-Vergleichstabelle  
    GET    /api/plans/pricing/             → Nur Preisinformationen
    GET    /api/plans/{id}/features/       → Features eines Plans

FEATURE ENDPOINTS:
    GET    /api/plans/features/            → Alle Features
    POST   /api/plans/features/            → Feature erstellen
    GET    /api/plans/features/{id}/       → Einzelnes Feature
    PUT    /api/plans/features/{id}/       → Feature bearbeiten
    PATCH  /api/plans/features/{id}/       → Feature teilweise bearbeiten
    DELETE /api/plans/features/{id}/       → Feature löschen
    GET    /api/plans/features/by_plan/    → Features gruppiert nach Plänen

PLAN-FEATURE ENDPOINTS:
    GET    /api/plans/plan-features/       → Alle Plan-Feature Zuordnungen
    POST   /api/plans/plan-features/       → Zuordnung erstellen
    GET    /api/plans/plan-features/{id}/  → Einzelne Zuordnung
    PUT    /api/plans/plan-features/{id}/  → Zuordnung bearbeiten
    PATCH  /api/plans/plan-features/{id}/  → Zuordnung teilweise bearbeiten
    DELETE /api/plans/plan-features/{id}/  → Zuordnung löschen

PERMISSIONS:
    - GET: Öffentlich zugänglich
    - POST/PUT/PATCH/DELETE: Nur für Staff/Admin

FILTER BEISPIELE:
    GET    /api/plans/?price_max=500                    → Pläne unter 500€
    GET    /api/plans/?has_feature=whitelabel          → Pläne mit Whitelabel
    GET    /api/plans/?min_minutes=500                 → Pläne mit min. 500 Min
    GET    /api/plans/?enterprise_only=true           → Nur Enterprise Pläne
    GET    /api/plans/?affordable_plans=true          → Erschwingliche Pläne
    GET    /api/plans/?ordering=price_monthly         → Sortiert nach Preis
    GET    /api/plans/?search=Pro                     → Suche nach "Pro"
""" 