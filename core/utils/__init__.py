from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging
from django.http import HttpResponse, Http404, FileResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views import View
from django.core.cache import cache
import os
import mimetypes
from django.utils import timezone
from decimal import Decimal, InvalidOperation


logger = logging.getLogger(__name__)


def create_user_workspace(user):
    """
    Create a default workspace for a newly registered user
    
    Args:
        user: User instance for whom to create workspace
        
    Returns:
        Workspace instance or None if creation failed
        
    Raises:
        Exception: If workspace creation fails critically
    """
    from core.models import Workspace
    
    try:
        # Generate workspace name
        base_name = f"{user.first_name} {user.last_name} Workspace".strip()
        
        # Ensure uniqueness by checking for existing names
        workspace_name = base_name
        counter = 1
        
        while Workspace.objects.filter(workspace_name=workspace_name).exists():
            workspace_name = f"{base_name} {counter}"
            counter += 1
            
        # Create workspace and set initial admin/creator to the user
        workspace = Workspace.objects.create(
            workspace_name=workspace_name,
            creator=user,
            admin_user=user,
        )
        
        # Link user to workspace
        workspace.users.add(user)
        
        # Auto-assign a default phone number from the global pool (idempotent)
        try:
            from core.services.phone_assignment import assign_default_number_to_workspace, WorkspacePhoneAssignmentError
            assign_default_number_to_workspace(workspace)
        except WorkspacePhoneAssignmentError:
            # No eligible global default numbers available; non-blocking
            pass
        except Exception:
            # Do not break registration flow on unexpected assignment issues
            pass
        
        logger.info(f"Successfully created workspace '{workspace_name}' for user {user.email}")
        return workspace
        
    except Exception as e:
        logger.error(f"Failed to create workspace for user {user.email}: {str(e)}")
        # Don't raise exception to avoid breaking registration flow
        return None


def send_email_verification(user, request=None):
    """
    Send email verification email to user
    """
    try:
        # Generate verification token
        token = user.generate_email_verification_token()
        
        # Build verification URL
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        verification_url = f"{base_url}/api/auth/verify-email/{token}/"
        
        # Email content
        subject = 'Bestätige deine E-Mail-Adresse - Hotcalls'
        
        # Create HTML email template content
        html_content = f"""
        <html>
        <head>
          <meta charset="UTF-8">
          <style>
            body {{
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
              line-height: 1.6;
              color: #333;
              margin: 0;
              padding: 0;
              background-color: #f5f5f5;
            }}
            .container {{
              max-width: 600px;
              margin: 0 auto;
              background-color: #ffffff;
            }}
            .header {{
              background: linear-gradient(135deg, #ff6b35 0%, #ff8c42 100%);
              padding: 40px 20px;
              text-align: center;
            }}
            .logo {{
              max-width: 180px;
              height: auto;
              margin-bottom: 20px;
            }}
            h1 {{
              color: #fff;
              margin: 0;
              font-size: 28px;
              font-weight: 600;
              letter-spacing: -0.5px;
            }}
            .content {{
              padding: 40px 30px;
            }}
            h2 {{
              color: #333;
              margin-top: 0;
              font-size: 22px;
              font-weight: 500;
            }}
            p {{
              color: #555;
              line-height: 1.6;
            }}
            .button {{
              display: inline-block;
              padding: 14px 32px;
              background: #ff6b35;
              color: #fff !important;
              text-decoration: none;
              border-radius: 6px;
              margin: 30px 0;
              font-weight: 600;
              font-size: 16px;
              transition: background 0.3s ease;
            }}
            .button:hover {{
              background: #ff8c42;
            }}
            .important {{
              background-color: #fff4f0;
              border-left: 4px solid #ff6b35;
              padding: 15px 20px;
              margin: 25px 0;
              border-radius: 4px;
            }}
            .footer {{
              padding: 30px;
              text-align: center;
              color: #666;
              font-size: 14px;
              background-color: #f9f9f9;
              border-top: 1px solid #e9ecef;
            }}
            .link {{
              color: #ff6b35;
              text-decoration: none;
            }}
            .link:hover {{
              text-decoration: underline;
            }}
          </style>
        </head>
        <body>
          <div class="container">
            <!-- Header -->
            <div class="header">
              <img src="https://app.hotcalls.ai/HC%20Logo.png" alt="Hotcalls Logo" class="logo">
              <h1>Willkommen bei Hotcalls!</h1>
            </div>
        
            <!-- Content -->
            <div class="content">
              <h2>Hallo {user.first_name or 'dort'} 👋</h2>
              <p>Schön, dass du dich bei Hotcalls registriert hast!</p>
        
              <p>Um deine Registrierung abzuschließen und direkt loszulegen, bestätige bitte deine E-Mail-Adresse:</p>
        
              <div style="text-align: center;">
                <a href="{verification_url}" class="button">E-Mail-Adresse bestätigen</a>
              </div>
        
              <p style="color: #999; font-size: 14px; text-align: center;">
                Falls der Button nicht funktioniert, kopiere diesen Link in deinen Browser:
              </p>
              <p style="word-break: break-all; text-align: center;">
                <a href="{verification_url}" class="link" style="font-size: 14px;">{verification_url}</a>
              </p>
        
              <div class="important">
                <p><strong>Wichtig:</strong> Ohne bestätigte E-Mail-Adresse kannst du dich nicht in dein Konto einloggen.</p>
              </div>
        
              <p>Falls du kein Konto bei uns erstellt hast, kannst du diese Nachricht einfach ignorieren.</p>
        
              <p>Viel Erfolg mit Hotcalls!</p>
        
              <p style="margin-top: 30px;">
                Beste Grüße,<br>
                <strong>Dein Hotcalls Team</strong>
              </p>
            </div>
        
            <!-- Footer -->
            <div class="footer">
              <p>Diese E-Mail wurde automatisch von Hotcalls versendet.</p>
              <p>Fragen? <a href="mailto:support@hotcalls.com" class="link">support@hotcalls.com</a></p>
              <p style="margin-top: 20px; font-size: 12px; color: #999;">
                © 2024 Hotcalls. Alle Rechte vorbehalten.
              </p>
            </div>
          </div>
        </body>
        </html>

        """
        
        # Plain text version
        text_content = f"""
        Willkommen bei Hotcalls!

        Hallo {user.first_name or 'dort'} 👋
        
        Schön, dass du dich bei Hotcalls registriert hast!
        
        Um deine Registrierung abzuschließen, bestätige bitte deine E-Mail-Adresse über diesen Link:
        
        {verification_url}
        
        Wichtig: Ohne bestätigte E-Mail-Adresse kannst du dich nicht in dein Konto einloggen.
        
        Falls du kein Konto bei uns erstellt hast, kannst du diese Nachricht einfach ignorieren.
        
        Viel Erfolg mit Hotcalls!
        
        Beste Grüße,
        Dein Hotcalls Team
        
        ---
        Diese E-Mail wurde automatisch von Hotcalls versendet.
        Bei Fragen: support@hotcalls.com
        © 2024 Hotcalls. Alle Rechte vorbehalten.
        """
        
        # Send email
        success = send_mail(
            subject=subject,
            message=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hotcalls.com'),
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
        
        if success:
            logger.info(f"Verification email sent successfully to {user.email}")
            return True
        else:
            logger.error(f"Failed to send verification email to {user.email}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending verification email to {user.email}: {str(e)}")
        return False


def send_password_reset_email(user, reset_token, request=None):
    """
    Send password reset email to user
    """
    try:
        # Build reset URL
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        reset_url = f"{base_url}/api/auth/reset-password/{reset_token}/"
        
        # Email content
        subject = 'Reset your password - HotCalls'
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #dc3545; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f8f9fa; }}
                .button {{ 
                    display: inline-block; 
                    padding: 12px 24px; 
                    background-color: #dc3545; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin: 20px 0; 
                }}
                .footer {{ padding: 20px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Password Reset Request</h1>
                </div>
                <div class="content">
                    <h2>Hello {user.get_full_name()},</h2>
                    <p>We received a request to reset your password for your HotCalls account.</p>
                    
                    <a href="{reset_url}" class="button">Reset Password</a>
                    
                    <p>If the button doesn't work, copy and paste this link into your browser:</p>
                    <p><a href="{reset_url}">{reset_url}</a></p>
                    
                    <p>If you didn't request a password reset, please ignore this email. Your password will not be changed.</p>
                    
                    <p>This reset link will expire in 24 hours for security reasons.</p>
                </div>
                <div class="footer">
                    <p>This email was sent from HotCalls. If you have any questions, please contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Password Reset Request
        
        Hello {user.get_full_name()},
        
        We received a request to reset your password for your HotCalls account.
        
        To reset your password, visit this link:
        {reset_url}
        
        If you didn't request a password reset, please ignore this email. Your password will not be changed.
        
        This reset link will expire in 24 hours for security reasons.
        
        Best regards,
        The HotCalls Team
        """
        
        # Send email
        success = send_mail(
            subject=subject,
            message=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hotcalls.com'),
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
        
        if success:
            logger.info(f"Password reset email sent successfully to {user.email}")
            return True
        else:
            logger.error(f"Failed to send password reset email to {user.email}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending password reset email to {user.email}: {str(e)}")
        return False


def send_workspace_invitation_email(invitation, request=None):
    """
    Send workspace invitation email to the invited user
    
    Args:
        invitation: WorkspaceInvitation instance
        request: Optional request object for building URLs
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Build invitation URLs
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        # Always route users through the login first with a single encoded `next` that
        # already contains all parameters for the accept flow to avoid param loss.
        next_target = (
            f"/invitations/{invitation.token}/accept/?"
            f"invited_workspace={invitation.workspace.id}&skip_welcome=1"
        )
        from urllib.parse import quote
        login_first_url = f"{base_url}/login?next={quote(next_target, safe='')}"
        # Keep legacy paths for reference (unused in email, but kept for clarity)
        invitation_url = f"{base_url}/invitations/{invitation.token}/"
        accept_url = f"{base_url}/invitations/{invitation.token}/accept/"
        
        # Email content
        workspace_name = invitation.workspace.workspace_name
        inviter_name = invitation.invited_by.get_full_name() or invitation.invited_by.email
        subject = f'Einladung zu "{workspace_name}" - Hotcalls'
        
        # Create HTML email template content
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; }}
                .header {{ background: linear-gradient(135deg, #ff6b35 0%, #ff8c42 100%); padding: 40px 20px; text-align: center; }}
                .logo {{ max-width: 180px; height: auto; margin-bottom: 20px; }}
                .content {{ padding: 40px 30px; background-color: #ffffff; }}
                .invitation-box {{ 
                    background: #f8f9fa; 
                    border: 2px solid #e9ecef; 
                    border-radius: 8px; 
                    padding: 20px; 
                    margin: 20px 0; 
                    text-align: center;
                }}
                .workspace-name {{ 
                    font-size: 20px; 
                    font-weight: bold; 
                    color: #ff6b35; 
                    margin: 10px 0;
                }}
                .button {{ 
                    display: inline-block; 
                    padding: 14px 32px; 
                    background: #ff6b35;
                    color: white; 
                    text-decoration: none; 
                    border-radius: 6px; 
                    margin: 30px 0; 
                    font-weight: 600;
                    font-size: 16px;
                    transition: background 0.3s ease;
                }}
                .button:hover {{ background: #ff8c42; }}
                .important {{ 
                    background: #fff3cd; 
                    border: 1px solid #ffeaa7; 
                    border-radius: 4px; 
                    padding: 15px; 
                    margin: 20px 0; 
                }}
                .footer {{ 
                    padding: 30px; 
                    text-align: center; 
                    color: #666; 
                    font-size: 14px; 
                    background-color: #f9f9f9;
                    border-top: 1px solid #e9ecef;
                }}
                .link {{ color: #ff6b35; text-decoration: none; }}
                .link:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="color: white; margin: 0; font-size: 28px;">🏢 Workspace-Einladung</h1>
                </div>
                <div class="content">
                    <h2 style="color: #333; margin-top: 0;">Hallo! 👋</h2>
                    
                    <p><strong>{inviter_name}</strong> hat dich eingeladen, dem Workspace beizutreten:</p>
                    
                    <div class="invitation-box">
                        <div class="workspace-name">"{workspace_name}"</div>
                        <p style="margin: 5px 0; color: #666;">auf Hotcalls</p>
                    </div>
                    
                    <p>Mit Hotcalls kannst du professionelle KI-gestützte Anrufe durchführen und dein Team bei der Lead-Generierung unterstützen.</p>
                    
                <p style="text-align: center;">
                    <a href="{login_first_url}" class="button">🎯 Einladung jetzt annehmen</a>
                </p>
                
                <p style="text-align: center; margin: 20px 0; font-size: 14px; color: #666;">
                    ↑ Klicke hier, um der Einladung direkt zu folgen
                </p>
                
                <p>Falls der Button nicht funktioniert, kopiere diesen Link in deinen Browser:</p>
                <p><a href="{login_first_url}" class="link">{login_first_url}</a></p>
                    
                    <div class="important">
                        <p><strong>Wichtig:</strong> Diese Einladung ist 7 Tage gültig und kann nur von der eingeladenen E-Mail-Adresse ({invitation.email}) angenommen werden.</p>
                    </div>
                    
                    <p>Falls du diese Einladung nicht erwartet hast, kannst du diese E-Mail einfach ignorieren.</p>
                    
                    <p>Wir freuen uns darauf, dich im Team zu haben!</p>
                    
                    <p style="margin-top: 30px;">Beste Grüße,<br>
                    <strong>Dein Hotcalls Team</strong></p>
                </div>
                <div class="footer">
                    <p>Diese Einladung wurde von <strong>{inviter_name}</strong> über Hotcalls versendet</p>
                    <p>Bei Fragen: <a href="mailto:support@hotcalls.com" class="link">support@hotcalls.com</a></p>
                    <p style="margin-top: 20px; font-size: 12px; color: #999;">© 2024 Hotcalls. Alle Rechte vorbehalten.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""Workspace-Einladung - Hotcalls

Hallo!

{inviter_name} hat dich eingeladen, dem Workspace "{workspace_name}" auf Hotcalls beizutreten.

Mit Hotcalls kannst du professionelle KI-gestützte Anrufe durchführen und dein Team bei der Lead-Generierung unterstützen.

🎯 EINLADUNG ANNEHMEN (Login erforderlich):
{login_first_url}

Wichtig: Diese Einladung ist 7 Tage gültig und kann nur von der eingeladenen E-Mail-Adresse ({invitation.email}) angenommen werden.

Falls du diese Einladung nicht erwartet hast, kannst du diese E-Mail einfach ignorieren.

Wir freuen uns darauf, dich im Team zu haben!

Bei Fragen: support@hotcalls.com

Beste Grüße,
Dein Hotcalls Team"""
        
        # Send email
        success = send_mail(
            subject=subject,
            message=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hotcalls.com'),
            recipient_list=[invitation.email],
            html_message=html_content,
            fail_silently=False,
        )
        
        if success:
            logger.info(f"Workspace invitation email sent successfully to {invitation.email} for workspace {workspace_name}")
            return True
        else:
            logger.error(f"Failed to send workspace invitation email to {invitation.email}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending workspace invitation email to {invitation.email}: {str(e)}")
        return False


def _get_billing_period_end(workspace):
    """Safely get current billing period end for a workspace subscription."""
    try:
        subscription = getattr(workspace, 'current_subscription', None)
        if not subscription:
            return None
        from core.quotas import current_billing_window
        _, period_end = current_billing_window(subscription)
        return period_end
    except Exception as exc:
        logger.error(f"Failed to resolve billing period for workspace {getattr(workspace, 'id', '')}: {exc}")
        return None


def send_minutes_threshold_email(workspace, threshold: int) -> bool:
    """
    Send an upgrade notification email to the workspace admin when minutes threshold is reached.
    Only sends if an admin_user with email is present.
    """
    try:
        admin = getattr(workspace, 'admin_user', None)
        recipient = getattr(admin, 'email', None) if admin else None
        if not recipient:
            logger.info(
                f"Skipping minutes threshold email for workspace {workspace.id} - no admin_user email configured"
            )
            return False

        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        plans_url = f"{base_url}/plans"
        subject = f"Hinweis: {threshold}% deines Minutenkontingents erreicht – jetzt upgraden"

        html_content = f"""
        <html>
          <body style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.6;color:#333;\">
            <div style=\"max-width:640px;margin:0 auto;background:#fff;border:1px solid #eee;border-radius:8px;overflow:hidden;\">
              <div style=\"background:linear-gradient(135deg,#ff6b35 0%,#ff8c42 100%);padding:24px;color:white;\">
                <h1 style=\"margin:0;font-size:20px;\">Nutzungs-Hinweis</h1>
              </div>
              <div style=\"padding:24px;\">
                <p>Hallo {recipient},</p>
                <p>euer Workspace <strong>{workspace.workspace_name}</strong> hat <strong>{threshold}%</strong> des monatlichen Minutenkontingents erreicht.</p>
                <p>Um Unterbrechungen zu vermeiden, kannst du jetzt bequem den Plan upgraden:</p>
                <p style=\"text-align:center;margin:28px 0;\">
                  <a href=\"{plans_url}\" style=\"display:inline-block;background:#ff6b35;color:#fff;padding:12px 20px;border-radius:6px;text-decoration:none;font-weight:600;\">Jetzt upgraden</a>
                </p>
                <p style=\"color:#666;font-size:14px;\">Dieser Hinweis wird pro Abrechnungszeitraum nur einmal pro Schwelle versendet.</p>
              </div>
            </div>
          </body>
        </html>
        """

        text_content = (
            f"Nutzungs-Hinweis\n\n"
            f"Workspace '{workspace.workspace_name}' hat {threshold}% des Minutenkontingents erreicht.\n"
            f"Jetzt upgraden: {plans_url}\n"
            f"(Hinweis wird pro Abrechnungszeitraum nur einmal pro Schwelle versendet.)"
        )

        success = send_mail(
            subject=subject,
            message=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hotcalls.com'),
            recipient_list=[recipient],
            html_message=html_content,
            fail_silently=False,
        )
        if success:
            logger.info(
                f"Minutes threshold email ({threshold}%) sent to admin {recipient} for workspace {workspace.id}"
            )
            return True
        logger.error(
            f"Failed to send minutes threshold email ({threshold}%) to {recipient} for workspace {workspace.id}"
        )
        return False
    except Exception as exc:
        logger.error(f"Error sending minutes threshold email for workspace {getattr(workspace, 'id', '')}: {exc}")
        return False


def check_and_notify_minutes_threshold(workspace) -> None:
    """
    Check call_minutes usage against 90% and 75% thresholds and notify admin once per billing period.
    Order: 90% first, then 75%.
    """
    try:
        # Determine billing period end for cache scoping
        period_end = _get_billing_period_end(workspace)
        if period_end is None:
            return

        # Get usage status read-only
        from core.quotas import get_feature_usage_status_readonly
        usage = get_feature_usage_status_readonly(workspace, 'call_minutes')

        # Skip unlimited or undefined limits
        if not usage or usage.get('unlimited') or not usage.get('limit'):
            return

        used = usage.get('used')
        limit = usage.get('limit')
        if used is None or limit in (None, 0):
            return

        # Compute percentage safely
        try:
            percent = (Decimal(used) / Decimal(limit)) if Decimal(limit) > 0 else Decimal('0')
        except (InvalidOperation, ZeroDivisionError):
            return

        # Prepare cache window TTL (seconds until end of period)
        now = timezone.now()
        if period_end.tzinfo is None:
            # Ensure period_end is aware
            period_end = timezone.make_aware(period_end, timezone.get_current_timezone())
        ttl_seconds = int(max(1, (period_end - now).total_seconds()))

        # Thresholds to evaluate (in order)
        checks = [
            (Decimal('0.90'), 90, f"usage_alert_90:{workspace.id}:{period_end.isoformat()}"),
            (Decimal('0.75'), 75, f"usage_alert_75:{workspace.id}:{period_end.isoformat()}"),
        ]

        for threshold_value, threshold_pct, cache_key in checks:
            if percent >= threshold_value:
                already_notified = cache.get(cache_key)
                if already_notified:
                    continue
                sent = send_minutes_threshold_email(workspace, threshold_pct)
                if sent:
                    cache.set(cache_key, True, timeout=ttl_seconds)
                # Continue loop to potentially set both flags
    except Exception as exc:
        logger.error(
            f"Minutes threshold check failed for workspace {getattr(workspace, 'id', '')}: {exc}",
            exc_info=True,
        )
class CORSMediaView(View):
    """Custom view for serving media files with CORS headers"""
    
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def get(self, request, path):
        """Serve media files with CORS headers and Range support"""
        # Security check: ensure we're only serving files from MEDIA_ROOT
        media_root = str(settings.MEDIA_ROOT)
        file_path = os.path.join(media_root, path)
        file_path = os.path.normpath(file_path)
        
        # Prevent directory traversal
        if not file_path.startswith(media_root):
            raise Http404("File not found")
        
        # Check if file exists
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise Http404("File not found")
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Get content type
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'
        
        # Handle Range requests for audio/video streaming
        range_header = request.META.get('HTTP_RANGE')
        if range_header:
            # Parse range header
            ranges = range_header.replace('bytes=', '').split('-')
            start = int(ranges[0]) if ranges[0] else 0
            end = int(ranges[1]) if ranges[1] else file_size - 1
            
            # Ensure end doesn't exceed file size
            end = min(end, file_size - 1)
            content_length = end - start + 1
            
            # Open file and seek to start position
            file_obj = open(file_path, 'rb')
            file_obj.seek(start)
            
            # Create partial content response
            response = HttpResponse(
                file_obj.read(content_length),
                status=206,  # Partial Content
                content_type=content_type
            )
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Content-Length'] = str(content_length)
            file_obj.close()
        else:
            # Regular response for full file
            response = FileResponse(
                open(file_path, 'rb'),
                content_type=content_type
            )
            response['Content-Length'] = str(file_size)
        
        # Add CORS headers
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Range, Accept-Encoding'
        response['Access-Control-Expose-Headers'] = 'Content-Length, Content-Range, Accept-Ranges, Content-Type'
        
        # Add Range support headers
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'public, max-age=3600'
        
        # Add headers for better browser compatibility
        if content_type.startswith('audio/'):
            response['X-Content-Type-Options'] = 'nosniff'
        
        # Add filename for download
        filename = os.path.basename(file_path)
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response
    
    def options(self, request, path):
        """Handle preflight requests"""
        response = HttpResponse()
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Range'
        response['Access-Control-Max-Age'] = '3600'
        return response
