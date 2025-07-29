from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse


@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request, format=None):
    """
    API Root - Lists all available API endpoints
    """
    return Response({
        'message': 'Welcome to HotCalls API',
        'version': '1.0',
        'endpoints': {
            'authentication': {
                'login': reverse('auth_api:login', request=request, format=format),
                'register': reverse('auth_api:register', request=request, format=format),
                'profile': reverse('auth_api:profile', request=request, format=format),
            },
            'management': {
                'users': request.build_absolute_uri('/api/users/'),
                'workspaces': request.build_absolute_uri('/api/workspaces/'),
                'agents': request.build_absolute_uri('/api/agents/'),
                'leads': request.build_absolute_uri('/api/leads/'),
                'calls': request.build_absolute_uri('/api/calls/'),
                'calendars': request.build_absolute_uri('/api/calendars/'),
                'voices': request.build_absolute_uri('/api/voices/'),
                'subscriptions': request.build_absolute_uri('/api/subscriptions/'),
            },
            'documentation': {
                'swagger': reverse('swagger-ui', request=request, format=format),
                'redoc': reverse('redoc', request=request, format=format),
                'schema': reverse('schema', request=request, format=format),
            }
        }
    })
