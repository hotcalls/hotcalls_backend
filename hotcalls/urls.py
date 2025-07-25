"""
URL configuration for hotcalls project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator


class BothHttpAndHttpsSchemaGenerator(OpenAPISchemaGenerator):
    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        schema.schemes = ["http", "https"]
        return schema


def health_check(request):
    """Health check endpoint for Docker/Kubernetes."""
    return JsonResponse({"status": "ok"})


# Define main URL patterns to be used for both actual routing and swagger documentation
api_url_patterns = [
    # TODO: Uncomment these when the corresponding URL files are created
    # path('api/v1/voice/', include('core.voice_api.urls')),
    # path('api/v1/frontend/', include('core.frontend_api.urls')),
    # path('api/v1/widget/', include('core.widget_api.urls')),
    # path('api/v1/management/', include('core.management_api.urls')),
    # path('api/v1/checkin/', include('core.checkin_api.urls')),
    # path('api/v1/ppc/', include('core.ppc_api.urls')),
    # path('api/v1/prc/', include('core.prc_api.urls')),
    # path('api/v1/patients/', include('patients.urls')),  # Add patients app URLs
]

# Swagger/OpenAPI documentation setup
schema_view = get_schema_view(
    openapi.Info(
        title="HotCalls API",
        default_version='v1',
        description="API documentation for HotCalls application",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@hotcalls.example"),
        license=openapi.License(name="Proprietary"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    patterns=api_url_patterns,  # Use the predefined patterns
    generator_class=BothHttpAndHttpsSchemaGenerator,
)


urlpatterns = [
    path('admin/', admin.site.urls),
    *api_url_patterns,  # Unpack the API patterns here
    path('health/', health_check, name='health_check'),
    
    # Swagger UI endpoints
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
