from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
import json

from .models import WorkspaceInvitation


def invitation_detail(request, token):
    """
    Display invitation details page (public endpoint)
    """
    try:
        invitation = WorkspaceInvitation.objects.get(token=token)
        
        # Check if invitation is still valid
        is_valid = invitation.is_valid()
        
        context = {
            'invitation': {
                'token': invitation.token,
                'email': invitation.email,
                'workspace_name': invitation.workspace.workspace_name,
                'invited_by_name': invitation.invited_by.get_full_name() or invitation.invited_by.email,
                'created_at': invitation.created_at,
                'expires_at': invitation.expires_at,
                'is_valid': is_valid,
            }
        }
        
        return render(request, 'invitations/invitation_detail.html', context)
        
    except WorkspaceInvitation.DoesNotExist:
        context = {
            'error_message': 'Diese Einladung wurde nicht gefunden oder ist ungültig.'
        }
        return render(request, 'invitations/invitation_error.html', context, status=404)


@require_http_methods(["GET", "POST"])
def accept_invitation(request, token):
    """
    Accept workspace invitation
    - GET: From email link - redirects to login if needed, then auto-accepts
    - POST: From invitation detail form - accepts invitation
    """
    # Check if invitation exists first
    try:
        invitation = WorkspaceInvitation.objects.get(token=token)
    except WorkspaceInvitation.DoesNotExist:
        context = {
            'error_message': 'Diese Einladung wurde nicht gefunden oder ist ungültig.'
        }
        return render(request, 'invitations/invitation_error.html', context, status=404)
    
    # Check if invitation is valid
    if not invitation.is_valid():
        context = {
            'error_message': 'Diese Einladung ist abgelaufen oder ungültig.'
        }
        return render(request, 'invitations/invitation_error.html', context, status=400)
    
    # Handle GET requests (from email button)
    if request.method == 'GET':
        # If user is not authenticated, redirect to login with return URL
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        
        # If authenticated but wrong email, show error
        if request.user.email != invitation.email:
            context = {
                'error_message': f'Diese Einladung wurde an {invitation.email} gesendet, aber Sie sind als {request.user.email} angemeldet.'
            }
            return render(request, 'invitations/invitation_error.html', context, status=403)
        
        # Auto-accept the invitation and show success
        try:
            invitation.accept(request.user)
            # Redirect to SPA dashboard with workspace selection and skip welcome flow
            return redirect(f"/dashboard?joined_workspace={invitation.workspace.id}&skip_welcome=1")
        except ValueError as e:
            context = {'error_message': str(e)}
            return render(request, 'invitations/invitation_error.html', context, status=400)
        except Exception as e:
            context = {'error_message': 'Ein unerwarteter Fehler ist aufgetreten beim Beitreten zum Workspace.'}
            return render(request, 'invitations/invitation_error.html', context, status=500)
    
    # Handle POST requests (from invitation detail form)
    if not request.user.is_authenticated:
        context = {
            'error_message': 'Sie müssen angemeldet sein, um eine Einladung anzunehmen.'
        }
        return render(request, 'invitations/invitation_error.html', context, status=401)
    
    # Verify email matches for POST requests
    if request.user.email != invitation.email:
        context = {
            'error_message': f'Diese Einladung wurde an {invitation.email} gesendet, aber Sie sind als {request.user.email} angemeldet.'
        }
        return render(request, 'invitations/invitation_error.html', context, status=403)
    
    # Accept the invitation
    try:
        invitation.accept(request.user)
        return redirect(f"/dashboard?joined_workspace={invitation.workspace.id}&skip_welcome=1")
    except ValueError as e:
        context = {'error_message': str(e)}
        return render(request, 'invitations/invitation_error.html', context, status=400)
    except Exception as e:
        context = {'error_message': 'Ein unerwarteter Fehler ist aufgetreten beim Beitreten zum Workspace.'}
        return render(request, 'invitations/invitation_error.html', context, status=500)
