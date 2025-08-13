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
    Public invitation landing: keep it simple and send users to login flow.
    """
    try:
        # Ensure token exists (return proper error if not)
        WorkspaceInvitation.objects.get(token=token)
    except WorkspaceInvitation.DoesNotExist:
        context = {
            'error_message': 'Diese Einladung wurde nicht gefunden oder ist ungültig.'
        }
        return render(request, 'invitations/invitation_error.html', context, status=404)

    # Always redirect to the login page with next pointing to acceptance URL
    return redirect(f"/login?next=/invitations/{token}/accept/")


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
        # If not authenticated, send user to the standard login with a proper next parameter
        if not request.user.is_authenticated:
            return redirect(f"/login?next={request.get_full_path()}")

        # If authenticated, verify email and accept immediately
        if request.user.email != invitation.email:
            context = {
                'error_message': f'Diese Einladung wurde an {invitation.email} gesendet, aber Sie sind als {request.user.email} angemeldet.'
            }
            return render(request, 'invitations/invitation_error.html', context, status=403)

        try:
            invitation.accept(request.user)
            return redirect(f"/dashboard?joined_workspace={invitation.workspace.id}&skip_welcome=1")
        except ValueError as e:
            context = {'error_message': str(e)}
            return render(request, 'invitations/invitation_error.html', context, status=400)
        except Exception:
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
