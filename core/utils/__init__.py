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
import os
import mimetypes


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
            
        # Create workspace
        workspace = Workspace.objects.create(workspace_name=workspace_name)
        
        # Link user to workspace
        workspace.users.add(user)
        
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
        subject = 'Verify your email address - HotCalls'
        
        # Create HTML email template content
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f8f9fa; }}
                .button {{ 
                    display: inline-block; 
                    padding: 12px 24px; 
                    background-color: #28a745; 
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
                    <h1>Welcome to HotCalls!</h1>
                </div>
                <div class="content">
                    <h2>Hello {user.get_full_name()},</h2>
                    <p>Thank you for registering with HotCalls. To complete your registration and start using our services, please verify your email address by clicking the button below:</p>
                    
                    <a href="{verification_url}" class="button">Verify Email Address</a>
                    
                    <p>If the button doesn't work, copy and paste this link into your browser:</p>
                    <p><a href="{verification_url}">{verification_url}</a></p>
                    
                    <p><strong>Important:</strong> You must verify your email address before you can log in to your account.</p>
                    
                    <p>If you didn't create an account with us, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>This email was sent from HotCalls. If you have any questions, please contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
        Welcome to HotCalls!
        
        Hello {user.get_full_name()},
        
        Thank you for registering with HotCalls. To complete your registration and start using our services, please verify your email address by visiting this link:
        
        {verification_url}
        
        Important: You must verify your email address before you can log in to your account.
        
        If you didn't create an account with us, please ignore this email.
        
        If you have any questions, please contact our support team.
        
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
