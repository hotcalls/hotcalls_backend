from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)


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
