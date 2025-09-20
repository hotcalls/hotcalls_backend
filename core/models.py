from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import uuid
from django.utils import timezone
from django.core.validators import MinValueValidator
import os
import datetime
import secrets


# New CallStatus TextChoices
class CallStatus(models.TextChoices):
    SCHEDULED = 'scheduled', 'scheduled'         # will be called
    CALL_TRIGGERED = 'call_triggered', 'call_triggered'  # trigger_call task spawned
    IN_PROGRESS = 'in_progress', 'in_progress'   # call in progress
    RETRY = 'retry', 'retry'                     # was called but failed 
    WAITING = 'waiting', 'waiting'               # limit hit


class DisconnectionReason(models.TextChoices):
    """Call disconnection reasons based on Retell AI standards"""
    # Expected behaviors - call ended successfully
    USER_HANGUP = 'user_hangup', 'User Hangup'
    AGENT_HANGUP = 'agent_hangup', 'Agent Hangup'
    CALL_TRANSFER = 'call_transfer', 'Call Transfer'
    VOICEMAIL_REACHED = 'voicemail_reached', 'Voicemail Reached'
    INACTIVITY = 'inactivity', 'Inactivity Timeout'
    MAX_DURATION_REACHED = 'max_duration_reached', 'Maximum Duration Reached'
    
    # Call not connected - outbound call failures
    DIAL_BUSY = 'dial_busy', 'Dial Busy'
    DIAL_FAILED = 'dial_failed', 'Dial Failed'
    DIAL_NO_ANSWER = 'dial_no_answer', 'No Answer'
    INVALID_DESTINATION = 'invalid_destination', 'Invalid Destination'
    TELEPHONY_PROVIDER_PERMISSION_DENIED = 'telephony_provider_permission_denied', 'Telephony Provider Permission Denied'
    TELEPHONY_PROVIDER_UNAVAILABLE = 'telephony_provider_unavailable', 'Telephony Provider Unavailable'
    SIP_ROUTING_ERROR = 'sip_routing_error', 'SIP Routing Error'
    MARKED_AS_SPAM = 'marked_as_spam', 'Marked as Spam'
    USER_DECLINED = 'user_declined', 'User Declined'
    
    # System errors
    CONCURRENCY_LIMIT_REACHED = 'concurrency_limit_reached', 'Concurrency Limit Reached'
    NO_VALID_PAYMENT = 'no_valid_payment', 'No Valid Payment'
    SCAM_DETECTED = 'scam_detected', 'Scam Detected'
    ERROR_LLM_WEBSOCKET_OPEN = 'error_llm_websocket_open', 'LLM Websocket Open Error'
    ERROR_LLM_WEBSOCKET_LOST_CONNECTION = 'error_llm_websocket_lost_connection', 'LLM Websocket Lost Connection'
    ERROR_LLM_WEBSOCKET_RUNTIME = 'error_llm_websocket_runtime', 'LLM Websocket Runtime Error'
    ERROR_LLM_WEBSOCKET_CORRUPT_PAYLOAD = 'error_llm_websocket_corrupt_payload', 'LLM Websocket Corrupt Payload'
    ERROR_NO_AUDIO_RECEIVED = 'error_no_audio_received', 'No Audio Received'
    ERROR_ASR = 'error_asr', 'ASR Error'
    ERROR_HOTCALLS = 'error_hotcalls', 'HotCalls Error'
    ERROR_UNKNOWN = 'error_unknown', 'Unknown Error'
    ERROR_USER_NOT_JOINED = 'error_user_not_joined', 'User Not Joined'
    REGISTERED_CALL_TIMEOUT = 'registered_call_timeout', 'Registered Call Timeout'
    # Preflight
    PREFLIGHT_CALL_LOG_FAILED = 'preflight_call_log_failed', 'Preflight Call Log Failed'


# Enum Choices
USER_STATUS_CHOICES = [
    ('active', 'Active'),
    ('suspended', 'Suspended'),
    ('forever_disabled', 'Forever Disabled'),
]

BLACKLIST_STATUS_CHOICES = [
    ('temporary', 'Temporary'),
    ('forever', 'Forever'),
    ('suspended', 'Suspended'),
]

CALL_DIRECTION_CHOICES = [
    ('inbound', 'Inbound'),
    ('outbound', 'Outbound'),
]



AGENT_STATUS_CHOICES = [
    ('active', 'Active'),
    ('paused', 'Paused'),
]

SOCIAL_PROVIDER_CHOICES = [
    ('google', 'Google'),
    ('apple', 'Apple'),
    ('facebook', 'Facebook'),
]

INTEGRATION_PROVIDER_CHOICES = [
    ('meta', 'Meta (Facebook/Instagram)'),
    ('google', 'Google'),
    ('manual', 'Manual Entry'),
    ('custom-webhook', 'Custom Webhook'),
    ('csv', "CSV File"),
]

META_INTEGRATION_STATUS_CHOICES = [
    ('active', 'Active'),
    ('expired', 'Expired'),
    ('revoked', 'Revoked'),
    ('error', 'Error'),
    ('disconnected', 'Disconnected'),
]

INVITATION_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('accepted', 'Accepted'),
    ('expired', 'Expired'),
    ('cancelled', 'Cancelled'),
]

# Calendar provider and weekday choices for scheduling/event types
CALENDAR_PROVIDER_CHOICES = [
    ('google', 'Google'),
    ('outlook', 'Outlook'),
]

# 0 = Monday ... 6 = Sunday
WEEKDAY_CHOICES = [
    (0, 'Monday'),
    (1, 'Tuesday'),
    (2, 'Wednesday'),
    (3, 'Thursday'),
    (4, 'Friday'),
    (5, 'Saturday'),
    (6, 'Sunday'),
]

# Mapping role for calendars linked to an EventType
MAPPING_ROLE_CHOICES = [
    ('target', 'Target Booking Calendar'),
    ('conflict', 'Conflict Calendar'),
]

class FeatureUnit(models.TextChoices):
    """Feature unit types for subscription tracking"""
    MINUTE = 'minute', 'Minute'
    GENERAL_UNIT = 'general_unit', 'General Unit' 
    ACCESS = 'access', 'Access'
    REQUEST = 'request', 'Request'
    GIGABYTE = 'gb', 'Gigabyte'

class HTTPMethod(models.TextChoices):
    """HTTP method choices for EndpointFeature"""
    GET = 'GET', 'GET'
    POST = 'POST', 'POST'
    PUT = 'PUT', 'PUT'
    PATCH = 'PATCH', 'PATCH'
    DELETE = 'DELETE', 'DELETE'
    HEAD = 'HEAD', 'HEAD'
    OPTIONS = 'OPTIONS', 'OPTIONS'
    ANY = '*', 'Any Method'

# Legacy constants for backwards compatibility
FEATURE_UNIT_CHOICES = FeatureUnit.choices
HTTP_METHOD_CHOICES = HTTPMethod.choices




class CustomUserManager(BaseUserManager):
    """Custom manager for User model with email-based authentication"""
    
    def create_user(self, email, password=None, **extra_fields):
        """Create and return a regular user with an email and password"""
        if not email:
            raise ValueError('The Email field must be set')
        
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('status', 'active')
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Create and return a superuser with an email and password"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('status', 'active')
        extra_fields.setdefault('is_email_verified', True)  # Superusers are automatically verified
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        user = self.create_user(email, password, **extra_fields)
        
        # Auto-create workspace and assign Enterprise plan for superuser
        self._setup_superuser_workspace_and_plan(user)
        
        return user
    
    def _setup_superuser_workspace_and_plan(self, user):
        """Setup workspace and Enterprise plan for superuser"""
        from django.utils import timezone
        
        try:
            # Create workspace for superuser
            workspace = Workspace.objects.create(
                workspace_name=f"{user.first_name} {user.last_name} Admin Workspace".strip() or f"Admin Workspace ({user.email})"
            )
            workspace.users.add(user)
            
            # Auto-assign a default phone number from the global pool (idempotent)
            try:
                from core.services.phone_assignment import assign_default_number_to_workspace, WorkspacePhoneAssignmentError
                assign_default_number_to_workspace(workspace)
            except WorkspacePhoneAssignmentError:
                # No eligible global default numbers available; non-blocking
                pass
            except Exception:
                # Do not break superuser setup on unexpected assignment issues
                pass
            
            # REMOVED: No longer auto-assign Enterprise plan during superuser creation
            # Plans should only be assigned after successful Stripe checkout
            # This was causing duplicate WorkspaceSubscription records

            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Created workspace '{workspace.workspace_name}' for superuser {user.email} (no plan assigned)")
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to setup workspace/plan for superuser {user.email}: {str(e)}")
            # Don't raise exception to avoid breaking superuser creation


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model with email-based authentication and verification"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core authentication fields
    email = models.EmailField(
        unique=True,
        help_text="Email address used for login"
    )
    
    # Email verification fields
    is_email_verified = models.BooleanField(
        default=False,
        help_text="Whether the user's email has been verified"
    )
    email_verification_token = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        editable=False,
        help_text="Token for email verification (encrypted at rest)"
    )
    email_verification_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the verification email was last sent"
    )
    
    # Password reset fields
    password_reset_token = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        editable=False,
        help_text="Token for password reset (encrypted at rest)"
    )
    password_reset_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the password reset email was last sent"
    )
    
    # User profile fields
    first_name = models.CharField(
        max_length=150,
        help_text="User's first name"
    )
    last_name = models.CharField(
        max_length=150,
        help_text="User's last name"
    )
    phone = models.CharField(
        max_length=50,
        help_text="Phone number in international format"
    )
    
    # System fields
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this user account is active"
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Whether this user can access the admin site"
    )
    
    # Custom fields
    stripe_customer_id = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        help_text="Stripe customer ID for billing"
    )
    status = models.CharField(
        max_length=20, 
        choices=USER_STATUS_CHOICES, 
        default='active',
        help_text="User account status"
    )
    social_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Social media account ID"
    )
    social_provider = models.CharField(
        max_length=20,
        choices=SOCIAL_PROVIDER_CHOICES,
        null=True,
        blank=True,
        help_text="Social media provider"
    )
    
    # Timestamps
    date_joined = models.DateTimeField(
        default=timezone.now,
        help_text="When the user account was created"
    )
    last_login = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the user last logged in"
    )
    
    # Use email as the username field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    objects = CustomUserManager()
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']
    
    def __str__(self):
        return f"{self.email} ({self.get_full_name()})"
    
    def get_full_name(self):
        """Return the user's full name"""
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_short_name(self):
        """Return the user's first name"""
        return self.first_name
    
    def generate_email_verification_token(self):
        """Generate a new email verification token"""
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = timezone.now()
        self.save(update_fields=['email_verification_token', 'email_verification_sent_at'])
        return self.email_verification_token
    
    def verify_email(self, token):
        """Verify email with the provided token"""
        if self.email_verification_token == token and self.email_verification_token:
            self.is_email_verified = True
            self.email_verification_token = None
            self.email_verification_sent_at = None
            self.save(update_fields=['is_email_verified', 'email_verification_token', 'email_verification_sent_at'])
            return True
        return False
    
    def generate_password_reset_token(self):
        """Generate a new password reset token"""
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_sent_at = timezone.now()
        self.save(update_fields=['password_reset_token', 'password_reset_sent_at'])
        return self.password_reset_token
    
    def verify_password_reset_token(self, token):
        """Verify password reset token and check if it's still valid (24 hours)"""
        if not self.password_reset_token or self.password_reset_token != token:
            return False
        
        # Check if token is expired (24 hours)
        if self.password_reset_sent_at:
            expiry_time = self.password_reset_sent_at + datetime.timedelta(hours=24)
            if timezone.now() > expiry_time:
                return False
        
        return True
    
    def reset_password_with_token(self, token, new_password):
        """Reset password using the provided token"""
        if self.verify_password_reset_token(token):
            self.set_password(new_password)
            self.password_reset_token = None
            self.password_reset_sent_at = None
            self.save(update_fields=['password', 'password_reset_token', 'password_reset_sent_at'])
            return True
        return False
    
    def can_login(self):
        """Check if user can login (active and email verified)"""
        return self.is_active and self.status == 'active' and self.is_email_verified


class Voice(models.Model):
    """Voice configurations for agents"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voice_external_id = models.CharField(
        max_length=255, 
        help_text="External voice ID from provider (e.g., ElevenLabs voice ID)"
    )
    provider = models.CharField(
        max_length=50, 
        help_text="Voice provider (e.g., 'elevenlabs', 'openai', 'google')"
    )
    name = models.CharField(
        max_length=100, 
        help_text="Voice display name"
    )
    gender = models.CharField(
        max_length=20,
        choices=[
            ('male', 'Male'),
            ('female', 'Female'),
            ('neutral', 'Neutral'),
        ],
        help_text="Voice gender"
    )
    tone = models.CharField(
        max_length=50, 
        help_text="Voice tone/style"
    )
    recommend = models.BooleanField(
        default=False, 
        help_text="Recommended voice"
    )
    voice_sample = models.FileField(
        upload_to='voice_samples/',
        blank=True,
        null=True,
        help_text="Voice sample file (.wav or .mp3 format)"
    )
    voice_picture = models.ImageField(
        upload_to='voice_pictures/',
        blank=True,
        null=True,
        help_text="Voice picture file (.png or .jpg format)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.provider})"


class Plan(models.Model):
    """Subscription plans"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan_name = models.CharField(max_length=100, unique=True)
    features = models.ManyToManyField('Feature', through='PlanFeature', related_name='mapping_plan_features')
    
    # Stripe integration fields
    stripe_product_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        unique=True,
        help_text="Stripe Product ID (prod_xxx)"
    )
    stripe_price_id_monthly = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Stripe Price ID for monthly billing (price_xxx)"
    )
    stripe_price_id_yearly = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Stripe Price ID for yearly billing (price_xxx)"
    )
    price_monthly = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Monthly price in EUR"
    )
    price_yearly = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Yearly price in EUR"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Is this plan available for new subscriptions?"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.plan_name


class Feature(models.Model):
    """High-level features that can be assigned to plans"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, help_text="Feature description")
    unit = models.CharField(
        max_length=20,
        choices=FeatureUnit.choices,
        blank=True, 
        null=True,
        help_text="Unit type for this feature"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.feature_name


class EndpointFeature(models.Model):
    """
    Maps an API route (by Django route name or regex) to the Feature that governs it.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature = models.ForeignKey(
        Feature, 
        on_delete=models.CASCADE, 
        related_name='endpoint_features',
        help_text="Feature that governs this endpoint"
    )
    route_name = models.CharField(
        max_length=200, 
        db_index=True,
        help_text="Django route name or regex pattern for the endpoint"
    )
    http_method = models.CharField(
        max_length=10,
        choices=HTTPMethod.choices,
        default=HTTPMethod.ANY,
        help_text="HTTP method (GET, POST, etc.) or '*' for any method"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("route_name", "http_method")
        indexes = [
            models.Index(fields=['route_name']),
            models.Index(fields=['route_name', 'http_method']),
        ]

    def __str__(self):
        method_str = f" ({self.http_method})" if self.http_method else ""
        return f"{self.route_name}{method_str} → {self.feature.feature_name}"


class PlanFeature(models.Model):
    """Mapping table between Plan and Feature with limit"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
    limit = models.DecimalField(
        max_digits=15, 
        decimal_places=3, 
        help_text="Feature limit for this plan"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['plan', 'feature']
    
    def __str__(self):
        return f"{self.plan.plan_name} - {self.feature.feature_name} (limit: {self.limit})"


class Workspace(models.Model):
    """Workspaces that users can belong to"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_name = models.CharField(max_length=255)
    users = models.ManyToManyField(User, related_name='mapping_user_workspaces')
    # Ownership and administration
    creator = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_workspaces'
    )
    admin_user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='admin_workspaces'
    )
    

    # Subscription
    current_plan = models.ForeignKey(
        'Plan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workspaces',
        help_text="Current subscription plan"
    )
    
    # Trial tracking
    has_used_trial = models.BooleanField(
        default=False,
        help_text="Whether this workspace has used their trial period"
    )
    
    # Stripe integration
    stripe_customer_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Stripe Customer ID for billing"
    )
    stripe_subscription_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Current Stripe Subscription ID (sub_xxx)"
    )

    # NEW: Track current subscription status (mirrors Stripe)
    SUBSCRIPTION_STATUS_CHOICES = [
        ('none', 'None'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('unpaid', 'Unpaid'),
        ('cancelled', 'Cancelled'),
    ]

    subscription_status = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_STATUS_CHOICES,
        default='none',
        help_text="Current subscription status (mirrors Stripe status)"
    )
    # Per-workspace SMTP configuration (sender). Password is stored encrypted at rest.
    smtp_enabled = models.BooleanField(
        default=False,
        help_text="Enable outbound email via this workspace SMTP configuration"
    )
    smtp_host = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="SMTP hostname"
    )
    smtp_port = models.IntegerField(
        default=587,
        help_text="SMTP port"
    )
    smtp_use_tls = models.BooleanField(
        default=True,
        help_text="Use STARTTLS"
    )
    smtp_use_ssl = models.BooleanField(
        default=False,
        help_text="Use implicit SSL/TLS"
    )
    smtp_username = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="SMTP username"
    )
    smtp_password_encrypted = models.TextField(
        blank=True,
        default='',
        help_text="SMTP password (encrypted at rest)"
    )
    smtp_from_email = models.EmailField(
        blank=True,
        default='',
        help_text="Sender email address for outbound messages"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
    @property 
    def current_subscription(self):
        """Get current active subscription"""
        try:
            return self.workspacesubscription_set.get(is_active=True)
        except WorkspaceSubscription.DoesNotExist:
            return None

    def is_admin(self, user: 'User') -> bool:
        if user is None:
            return False
        return bool(self.admin_user and self.admin_user_id == user.id)
    
    class Meta:
        constraints = [
            # Ensure unique stripe_customer_id when not NULL
            models.UniqueConstraint(
                fields=['stripe_customer_id'], 
                condition=models.Q(stripe_customer_id__isnull=False),
                name='unique_stripe_customer_id'
            ),
            # Ensure unique stripe_subscription_id when not NULL
            models.UniqueConstraint(
                fields=['stripe_subscription_id'],
                condition=models.Q(stripe_subscription_id__isnull=False), 
                name='unique_stripe_subscription_id'
            ),
        ]
    
    def __str__(self):
        return self.workspace_name


class WorkspaceInvitation(models.Model):
    """Workspace invitations for inviting users via email"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core invitation fields
    workspace = models.ForeignKey(
        Workspace, 
        on_delete=models.CASCADE, 
        related_name='invitations',
        help_text="Workspace the user is being invited to"
    )
    email = models.EmailField(
        help_text="Email address of the person being invited"
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_invitations',
        help_text="User who sent the invitation"
    )
    
    # Invitation management
    token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Secure token for invitation acceptance (encrypted at rest)"
    )
    status = models.CharField(
        max_length=20,
        choices=INVITATION_STATUS_CHOICES,
        default='pending',
        help_text="Current status of the invitation"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="When this invitation expires (7 days from creation)"
    )
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the invitation was accepted"
    )
    
    class Meta:
        unique_together = ['workspace', 'email', 'status']
        constraints = [
            # Only one pending invitation per workspace-email combination
            models.UniqueConstraint(
                fields=['workspace', 'email'],
                condition=models.Q(status='pending'),
                name='unique_pending_invitation_per_workspace_email'
            )
        ]
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['email', 'status']),
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['expires_at']),
        ]
    
    def save(self, *args, **kwargs):
        # Set expiration to 7 days from now if not set
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        
        # Generate token if not set
        if not self.token:
            self.token = self.generate_token()
        
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_token():
        """Generate a secure random token for invitations"""
        return secrets.token_urlsafe(48)  # 64 character URL-safe token
    
    def is_valid(self):
        """Check if invitation is still valid (not expired and pending)"""
        return (
            self.status == 'pending' and 
            self.expires_at and 
            timezone.now() < self.expires_at
        )
    
    def accept(self, user):
        """Accept the invitation and add user to workspace"""
        if not self.is_valid():
            raise ValueError("Invitation is not valid or has expired")
        
        if user.email != self.email:
            raise ValueError("Email address does not match invitation")
        
        # Add user to workspace
        self.workspace.users.add(user)
        
        # Update invitation status
        self.status = 'accepted'
        self.accepted_at = timezone.now()
        self.save(update_fields=['status', 'accepted_at'])
        
        return True
    
    def cancel(self):
        """Cancel the invitation"""
        if self.status == 'pending':
            self.status = 'cancelled'
            self.save(update_fields=['status'])
    
    def __str__(self):
        return f"Invitation: {self.email} → {self.workspace.workspace_name} ({self.status})"


class WorkspaceSubscription(models.Model):
    """
    Makes the relationship between a Workspace and a Plan explicit,
    and captures periods so you can keep historical data.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    started_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # One active subscription at a time
        constraints = [
            models.UniqueConstraint(
                fields=["workspace"],
                condition=models.Q(is_active=True),
                name="unique_active_subscription_per_workspace"
            )
        ]

    def __str__(self):
        return f"{self.workspace.workspace_name} - {self.plan.plan_name} ({'Active' if self.is_active else 'Inactive'})"


class WorkspaceUsage(models.Model):
    """
    One record per workspace **per billing period**.
    Historical rows are never mutated – new row each period.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    subscription = models.ForeignKey(
        WorkspaceSubscription,
        on_delete=models.PROTECT,
        help_text="Subscription that was active for this usage period",
    )
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    # Extra purchased call minutes for the current billing period
    extra_call_minutes = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        default=0,
        help_text="Extra purchased call minutes credited to this billing period"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("workspace", "period_start", "period_end")

    def __str__(self):
        return f"{self.workspace} | {self.period_start:%Y-%m-%d} → {self.period_end:%Y-%m-%d}"


class FeatureUsage(models.Model):
    """
    Counter per feature inside a WorkspaceUsage container.
    used_amount is:
      • minutes   for unit='minute'
      • integer   for unit='general_unit' or 'access' (0 or 1)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usage_record = models.ForeignKey(
        WorkspaceUsage, related_name="feature_usages",
        on_delete=models.CASCADE
    )
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
    used_amount = models.DecimalField(max_digits=15, decimal_places=3, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("usage_record", "feature")

    def __str__(self):
        return f"{self.feature.feature_name} - {self.used_amount}"

    @property
    def limit(self):
        """
        Fetch the limit from PlanFeature (None = unlimited)
        """
        plan = self.usage_record.subscription.plan
        try:
            return plan.planfeature_set.get(feature=self.feature).limit
        except PlanFeature.DoesNotExist:
            return None

    @property
    def remaining(self):
        """
        Calculate remaining usage based on limit
        """
        lim = self.limit
        return None if lim is None else max(lim - self.used_amount, 0)


def agent_kb_upload_path(instance, filename):
    """Deterministic path for agent Knowledge Base PDF, like voices storage."""
    base_name = os.path.basename(filename)
    return f"kb/agents/{instance.agent_id}/{base_name}"

def agent_send_document_upload_path(instance, filename):
    """Storage path for the single PDF the agent can send via email."""
    base_name = os.path.basename(filename)
    return f"docs/agents/{instance.agent_id}/{base_name}"


class Agent(models.Model):
    """AI agents for each workspace"""
    agent_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='mapping_workspace_agents')
    
    # NEW: Agent identification and status
    name = models.CharField(
        max_length=255,
        help_text="Agent name for display"
    )
    status = models.CharField(
        max_length=10,
        choices=AGENT_STATUS_CHOICES,
        default='active',
        help_text="Agent status"
    )
    
    # UPDATED: Multiple greeting types
    greeting_inbound = models.TextField(
        help_text="Greeting for inbound calls",
        blank=True,
        default="Hello! How can I help you today?"
    )
    greeting_outbound = models.TextField(
        help_text="Greeting for outbound calls", 
        blank=True,
        default="Hello! I'm calling from our team. Is this a good time to talk?"
    )
    
    # UPDATED: Voice as relationship to Voice model
    voice = models.ForeignKey(
        Voice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agents',
        help_text="Voice configuration for this agent"
    )
    
    language = models.CharField(
        max_length=50, 
        help_text="Agent language",
        default="en"
    )
    retry_interval = models.IntegerField(
        help_text="Retry interval in minutes",
        default=30
    )
    max_retries = models.IntegerField(
        help_text="Maximum number of retry attempts for calls",
        default=3
    )
    max_call_duration_minutes = models.IntegerField(
        help_text="Maximum allowed call duration (minutes) before auto-cleanup of stuck IN_PROGRESS tasks",
        default=30
    )
    workdays = models.JSONField(
        default=list,
        help_text="List of working days, e.g., ['monday', 'tuesday', 'wednesday']",
        blank=True
    )
    call_from = models.TimeField(
        help_text="Start time for calls",
        default="09:00:00"
    )
    call_to = models.TimeField(
        help_text="End time for calls",
        default="17:00:00"
    )
    character = models.TextField(
        help_text="Agent character/personality description",
        blank=True,
        default="I am a helpful and professional AI assistant."
    )
    script_template = models.TextField(
        help_text="Script template/instructions for AI behavior",
        blank=True,
        default=""
    )
    # Knowledge Base: single PDF file stored like voices (no manifest)
    kb_pdf = models.FileField(
        upload_to=agent_kb_upload_path,
        null=True,
        blank=True,
        help_text="Single Knowledge Base PDF for this agent"
    )
    # Email sending configuration
    send_document = models.FileField(
        upload_to=agent_send_document_upload_path,
        null=True,
        blank=True,
        help_text="Single PDF that the agent can send via email"
    )
    email_default_subject = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Default subject when sending the document via email"
    )
    email_default_body = models.TextField(
        null=True,
        blank=True,
        help_text="Default body when sending the document via email"
    )
    config_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Configuration ID for agent settings"
    )
    phone_number = models.ForeignKey(
        'PhoneNumber',
        on_delete=models.PROTECT,
        related_name='agents',
        null=True,
        blank=True,
        help_text="Phone number assigned to this agent (agent accesses SIP trunk via agent.phone_number.sip_trunk)"
    )
    # calendar_configuration removed - CalendarConfiguration no longer exists
    
    # NEW: One-to-one mapping to EventType for booking
    event_type = models.OneToOneField(
        'EventType',
        on_delete=models.SET_NULL,
        related_name='agent',
        null=True,
        blank=True,
        help_text="Event type used by this agent for availability and booking"
    )
    
    # NEW: Agent claims ownership of a lead funnel
    lead_funnel = models.OneToOneField(
        'LeadFunnel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent',
        help_text="Lead funnel this agent handles"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.workspace.workspace_name})"


class SIPTrunk(models.Model):
    """SIP trunk configurations for outbound calling"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Provider credentials
    provider_name = models.CharField(
        max_length=100,
        help_text="SIP provider name (e.g., 'Twilio', 'Sipgate')"
    )
    sip_username = models.CharField(
        max_length=255,
        help_text="SIP authentication username"
    )
    sip_password = models.CharField(
        max_length=255,
        help_text="SIP authentication password (encrypted at rest)"
    )
    sip_host = models.CharField(
        max_length=255,
        help_text="SIP server domain/IP address"
    )
    sip_port = models.IntegerField(
        default=5060,
        help_text="SIP server port"
    )
    
    # External integration IDs
    jambonz_carrier_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Jambonz carrier ID for this trunk"
    )
    livekit_trunk_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="LiveKit trunk ID for this provider"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this SIP trunk is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.provider_name} - {self.sip_host}"


class PhoneNumber(models.Model):
    """Phone numbers that can be shared across multiple agents"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phonenumber = models.CharField(
        max_length=17,
        unique=True,
        help_text="Phone number in E.164 format"
    )
    # Marks numbers that belong to the global default pool (eligible for new workspaces)
    is_global_default = models.BooleanField(
        default=False,
        help_text="If true, number is eligible for round-robin assignment to new workspaces"
    )
    
    # TRUNK RELATIONSHIP - Each phone number has ONE SIP trunk
    sip_trunk = models.OneToOneField(
        SIPTrunk,
        on_delete=models.CASCADE,
        related_name='phone_number',
        null=True,
        blank=True,
        help_text="SIP trunk associated with this phone number"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this phone number is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.phonenumber


class WorkspacePhoneNumber(models.Model):
    """Mapping of workspace to phone numbers with a workspace-level default flag."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'Workspace',
        on_delete=models.CASCADE,
        related_name='workspace_phonenumbers',
        help_text="Workspace that can use this phone number"
    )
    phone_number = models.ForeignKey(
        PhoneNumber,
        on_delete=models.CASCADE,
        related_name='workspace_mappings',
        help_text="Phone number available to this workspace"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="If true, default phone number for this workspace"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'phone_number'], name='uq_workspace_phone_number')
        ]

    def __str__(self):
        return f"{self.workspace.workspace_name} → {self.phone_number.phonenumber} ({'default' if self.is_default else 'pool'})"


class Lead(models.Model):
    """Leads that agents will call"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    surname = models.CharField(max_length=255, blank=True, null=True, help_text="Lead surname")
    email = models.EmailField()
    phone = models.CharField(
        max_length=50,
        help_text="Lead's phone number"
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='leads',
        null=True,  # Will be made non-nullable after backfill migration
        blank=True,
        help_text="Workspace this lead belongs to"
    )
    integration_provider = models.CharField(
        max_length=20,
        choices=INTEGRATION_PROVIDER_CHOICES,
        null=True,
        blank=True,
        help_text="Integration provider source"
    )
    variables = models.JSONField(
        default=dict,
        help_text="Concrete lead variables from integration"
    )
    
    # NEW: Lead knows which funnel it came from
    lead_funnel = models.ForeignKey(
        'LeadFunnel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leads',
        help_text="Source funnel this lead came from"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    meta_data = models.JSONField(
        default=dict,
        help_text="Custom JSON data for the lead"
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.phone})"


class Blacklist(models.Model):
    """Blacklisted users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='mapping_user_blacklist')
    reason = models.TextField(help_text="Reason for blacklisting")
    status = models.CharField(
        max_length=20, 
        choices=BLACKLIST_STATUS_CHOICES,
        help_text="Blacklist status"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Blacklist: {self.user.email} ({self.status})"


class CallLog(models.Model):
    """Call logs for tracking all calls"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Lead is optional to support calls without a stored lead
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='mapping_lead_calllogs', null=True, blank=True)
    agent = models.ForeignKey(
        Agent, 
        on_delete=models.CASCADE, 
        related_name='mapping_agent_calllogs',
        help_text="Agent who made/received the call"
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='call_logs',
        help_text="Workspace this call log belongs to"
    )
    # Persist the originating CallTask identifier without FK to allow dangling reference
    call_task_id = models.UUIDField(default=uuid.uuid4, help_text="ID of originating CallTask (not a foreign key, may be dangling)")
    # Persist canonical target reference from CallTask (e.g., 'lead:<uuid>')
    target_ref = models.CharField(max_length=255, null=True, blank=True, help_text="Canonical call target reference from CallTask")
    # Idempotency key for a single call attempt (unique per event)
    event_id = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Idempotency key for a single call attempt (one CallLog per event_id)"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    from_number = models.CharField(max_length=20, help_text="Caller's phone number")
    to_number = models.CharField(max_length=20, help_text="Recipient's phone number")
    duration = models.IntegerField(help_text="Call duration in seconds")
    disconnection_reason = models.CharField(
        max_length=50,
        choices=DisconnectionReason.choices,
        null=True, 
        blank=True, 
        help_text="Reason for call disconnection"
    )
    direction = models.CharField(
        max_length=10, 
        choices=CALL_DIRECTION_CHOICES, 
        help_text="Call direction"
    )
    # Removed redundant status; use disconnection_reason and appointment_datetime if applicable
    appointment_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Scheduled appointment datetime when status is 'appointment_scheduled'"
    )
    transcript = models.JSONField(
        null=True, 
        blank=True,
        help_text="Complete conversation transcript as JSON array of messages"
    )
    summary = models.TextField(
        null=True, 
        blank=True, 
        help_text="AI-generated summary of the call transcript"
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Call: {self.from_number} → {self.to_number} ({self.timestamp})"




class Calendar(models.Model):
    """Generic calendar - provider agnostic"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'Workspace', 
        on_delete=models.CASCADE, 
        related_name='calendars'
    )
    name = models.CharField(max_length=255, default='', help_text="Display name for the calendar")
    provider = models.CharField(
        max_length=20, 
        choices=[
            ('google', 'Google Calendar'),
            ('outlook', 'Outlook Calendar'),
        ],
        default='google'
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['workspace', 'name', 'provider']
        indexes = [
            models.Index(fields=['workspace', 'provider', 'active']),
        ]
    
    def delete(self, *args, **kwargs):
        """Properly disconnect and clean up provider-specific resources before deletion"""
        
        # Handle Google Calendar cleanup
        if self.provider == 'google' and hasattr(self, 'google_calendar'):
            try:
                from core.services.google_calendar import GoogleCalendarService
                service = GoogleCalendarService()
                service.revoke_tokens(self.google_calendar)
            except Exception as e:
                # Log but don't fail - we still want to delete
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to revoke Google tokens for calendar {self.id}: {e}")
        
        # Handle Outlook Calendar cleanup
        elif self.provider == 'outlook' and hasattr(self, 'outlook_calendar'):
            try:
                from core.services.outlook_calendar import OutlookCalendarService
                service = OutlookCalendarService()
                service.revoke_tokens(self.outlook_calendar)
            except Exception as e:
                # Log but don't fail - we still want to delete
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to revoke Outlook tokens for calendar {self.id}: {e}")
        
        # Now delete the Calendar (will cascade to provider models and sub-accounts)
        super().delete(*args, **kwargs)
    
    def __str__(self):
        return f"{self.workspace.workspace_name} - {self.name} ({self.provider})"


class GoogleCalendar(models.Model):
    """Google Calendar with OAuth credentials and metadata"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.OneToOneField(
        'Calendar', 
        on_delete=models.CASCADE, 
        related_name='google_calendar'
    )
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='google_calendars',
        help_text="User who connected this calendar"
    )
    
    # OAuth credentials (from old GoogleCalendarConnection)
    account_email = models.EmailField(help_text="Google account email")
    refresh_token = models.TextField(editable=False, help_text="OAuth refresh token (encrypted at rest)")
    access_token = models.TextField(editable=False, help_text="OAuth access token (encrypted at rest)")
    token_expires_at = models.DateTimeField(help_text="When access token expires")
    scopes = models.JSONField(
        default=list,
        help_text="Granted OAuth scopes"
    )
    
    # Google Calendar API fields
    external_id = models.CharField(
        max_length=255, 
        unique=True,
        help_text="Google Calendar ID"
    )
    time_zone = models.CharField(max_length=50)
    access_role = models.CharField(
        max_length=20,
        choices=[
            ('freeBusyReader', 'Free/Busy Reader'),
            ('reader', 'Reader'),
            ('writer', 'Writer'),
            ('owner', 'Owner'),
        ],
        default='reader',
        help_text="Access level for this calendar"
    )
    
    # Sync status
    last_sync = models.DateTimeField(null=True, blank=True)
    sync_errors = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['token_expires_at']),
            models.Index(fields=['account_email']),
        ]
    
    def __str__(self):
        return f"{self.calendar.name} - {self.account_email} ({self.external_id})"


# MicrosoftCalendarConnection removed - merged into OutlookCalendar model


class OutlookCalendar(models.Model):
    """Outlook Calendar with OAuth credentials and metadata"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.OneToOneField(
        'Calendar',
        on_delete=models.CASCADE,
        related_name='outlook_calendar'
    )
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='outlook_calendars',
        help_text="User who connected this calendar"
    )

    # OAuth credentials (from old MicrosoftCalendarConnection)
    primary_email = models.EmailField(help_text="Primary UPN/email of the Microsoft account")
    tenant_id = models.CharField(max_length=128, help_text="Azure AD Tenant ID (tid)")
    ms_user_id = models.CharField(max_length=128, help_text="Microsoft user object ID (oid)")
    display_name = models.CharField(max_length=255, blank=True, default='')
    timezone_windows = models.CharField(max_length=100, blank=True, default='', help_text="Windows time zone id (e.g., 'W. Europe Standard Time')")
    refresh_token = models.TextField(editable=False, help_text="OAuth refresh token (encrypted at rest)")
    access_token = models.TextField(editable=False, help_text="OAuth access token (encrypted at rest)")
    token_expires_at = models.DateTimeField(help_text="When access token expires")
    scopes_granted = models.JSONField(default=list, help_text="Granted OAuth scopes")

    # Graph Calendar fields
    external_id = models.CharField(max_length=255, unique=True, help_text="Microsoft Calendar ID")
    can_edit = models.BooleanField(default=True, help_text="Whether current user can edit this calendar")

    # Sync status
    last_sync = models.DateTimeField(null=True, blank=True)
    sync_errors = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['token_expires_at']),
            models.Index(fields=['primary_email']),
        ]

    def __str__(self):
        return f"{self.calendar.name} - {self.primary_email} ({self.external_id})"


# MicrosoftSubscription removed - not needed for OAuth only

# CalendarConfiguration removed - no longer needed


class GoogleSubAccount(models.Model):
    """
    A target Google identity you act as (e.g., delegated user, shared/resource calendar owner,
    or domain-wide delegation subject).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    google_calendar = models.ForeignKey(
        'GoogleCalendar', 
        on_delete=models.CASCADE, 
        related_name='sub_accounts',
        help_text="The main Google account that owns the OAuth tokens"
    )
    act_as_email = models.EmailField(help_text="Target user/resource email you operate on behalf of")
    act_as_user_id = models.CharField(
        max_length=128, 
        blank=True, 
        default='', 
        help_text="Google user id if known"
    )
    calendar_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Human-readable calendar name (e.g. 'Focus Time' instead of cryptic ID)"
    )
    relationship = models.CharField(
        max_length=32,
        choices=[
            ('self', 'Self / same user'),
            ('shared', 'Shared calendar'),
            ('delegate', 'Delegated access'),
            ('domain_impersonation', 'Domain-wide delegation (service account)'),
            ('resource', 'Resource calendar'),
        ],
        default='self'
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('google_calendar', 'act_as_email')]
        indexes = [
            models.Index(fields=['act_as_email']),
            models.Index(fields=['google_calendar', 'active']),
        ]

    def __str__(self):
        # Show calendar name if available, otherwise show truncated email/ID
        if hasattr(self, 'calendar_name') and self.calendar_name:
            return f"{self.calendar_name} ({self.relationship})"
        # For calendar IDs, just show the first part before @
        email_part = self.act_as_email.split('@')[0]
        if len(email_part) > 30:
            email_part = email_part[:30] + "..."
        return f"{email_part} ({self.relationship})"


class OutlookSubAccount(models.Model):
    """
    A target Microsoft mailbox you act as (UPN/email). Works for shared/delegated mailboxes
    or app-only impersonation (/users/{upn}/calendars).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outlook_calendar = models.ForeignKey(
        'OutlookCalendar', 
        on_delete=models.CASCADE, 
        related_name='sub_accounts',
        help_text="The main Outlook account that owns the OAuth tokens"
    )
    act_as_upn = models.EmailField(help_text="Target mailbox (UPN/email)")
    # NEW: Persist per-calendar identity similar to GoogleSubAccount
    calendar_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Microsoft Graph calendar id for this sub-account"
    )
    calendar_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Human-readable calendar name"
    )
    mailbox_object_id = models.CharField(
        max_length=128, 
        blank=True, 
        default='',
        help_text="AAD user object id if known"
    )
    is_default_calendar = models.BooleanField(default=False)
    relationship = models.CharField(
        max_length=32,
        choices=[
            ('self', 'Self / same user'),
            ('shared', 'Shared mailbox/calendar'),
            ('delegate', 'Delegated access'),
            ('app_only', 'Application-permission impersonation'),
            ('resource', 'Room/equipment'),
        ],
        default='self'
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('outlook_calendar', 'act_as_upn', 'calendar_id')]
        indexes = [
            models.Index(fields=['act_as_upn']),
            models.Index(fields=['calendar_id']),
            models.Index(fields=['outlook_calendar', 'active']),
        ]

    def __str__(self):
        return f"{self.act_as_upn} via {self.outlook_calendar.primary_email}"



# =============================
# Scheduling: Event Types layer
# =============================

class SubAccount(models.Model):
    """
    Provider-agnostic router pointing to provider-specific sub-account (Google/Outlook).
    Stores the provider and the provider-specific subaccount primary key as string.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    provider = models.CharField(
        max_length=20,
        choices=CALENDAR_PROVIDER_CHOICES,
        help_text="Calendar provider for this sub-account",
    )

    # If provider='google'  -> stores GoogleSubAccount.id as string
    # If provider='outlook' -> stores OutlookSubAccount.id as string
    sub_account_id = models.CharField(
        max_length=255,
        help_text="Primary key of the provider-specific subaccount (stored as string)",
    )

    # User who connected/owns this integration
    owner = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='calendar_subaccounts',
        help_text="User who owns/connected this sub-account",
    )

    # Note: we intentionally do NOT persist target email/UPN or calendar_id here
    # to keep this router minimal and provider-agnostic.

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "provider", "sub_account_id"],
                name="uq_owner_provider_subaccount",
            )
        ]

    def __str__(self):
        return f"{self.get_provider_display()} — {self.sub_account_id}"


class EventType(models.Model):
    """
    Scheduling event type (meeting template) with timing rules and calendar links.
    No is_active flag by design.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    workspace = models.ForeignKey(
        'Workspace',
        on_delete=models.CASCADE,
        related_name='event_types',
        help_text="Workspace that owns this event type",
    )

    created_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_event_types',
        help_text="User who created this event type",
    )

    name = models.CharField(max_length=255, help_text="Display name for the event type")

    # Duration in minutes
    duration = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Duration in minutes",
    )

    # IANA timezone string (e.g., Europe/Berlin)
    timezone = models.CharField(
        max_length=64,
        default='UTC',
        help_text="IANA timezone name used to interpret working hours",
    )

    # Buffer BEFORE  the meeting, in HOURS
    buffer_time = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Buffer time in HOURS to leave before each booking",
    )

    # Prep BEFORE the meeting, in MINUTES
    prep_time = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Preparation time in MINUTES to block before each booking",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # M2M via explicit mapping
    sub_accounts = models.ManyToManyField(
        'SubAccount',
        through='EventTypeSubAccountMapping',
        related_name='event_types',
    )

    def __str__(self):
        return f"{self.name} ({self.workspace.workspace_name})"


class EventTypeSubAccountMapping(models.Model):
    """
    Many-to-many mapping between EventType and SubAccount with a role flag.
    role='target'   → destination for bookings; also used for conflicts
    role='conflict' → only used for free/busy checks
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    event_type = models.ForeignKey(
        'EventType',
        on_delete=models.CASCADE,
        related_name='calendar_mappings',
    )
    sub_account = models.ForeignKey(
        'SubAccount',
        on_delete=models.CASCADE,
        related_name='event_type_mappings',
    )

    role = models.CharField(
        max_length=16,
        choices=MAPPING_ROLE_CHOICES,
        help_text="Target = booking destination; Conflict = availability checks only",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'event_type_subaccount_mapping'
        constraints = [
            models.UniqueConstraint(
                fields=['event_type', 'sub_account'],
                name='uq_eventtype_subaccount',
            ),
        ]

    def __str__(self):
        return f"{self.event_type_id} ↔ {self.sub_account_id} ({self.role})"


class EventTypeWorkingHour(models.Model):
    """
    Per-day working hours for an EventType. Times interpreted in EventType.timezone.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    event_type = models.ForeignKey(
        'EventType',
        on_delete=models.CASCADE,
        related_name='working_hours',
    )
    day_of_week = models.PositiveSmallIntegerField(
        choices=WEEKDAY_CHOICES,
        help_text='0=Monday … 6=Sunday',
    )
    start_time = models.TimeField(help_text="Local start time in the event type's timezone")
    end_time = models.TimeField(help_text="Local end time (must be after start_time)")

    class Meta:
        db_table = 'event_type_working_hour'
        constraints = [
            models.UniqueConstraint(
                fields=['event_type', 'day_of_week'],
                name='uq_eventtype_weekday',
            ),
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')),
                name='chk_workinghour_start_before_end',
            ),
        ]

    def __str__(self):
        return f"{self.event_type_id} — {self.get_day_of_week_display()} {self.start_time}–{self.end_time}"

class MetaIntegration(models.Model):
    """Meta (Facebook/Instagram) integration for workspaces"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace, 
        on_delete=models.CASCADE, 
        related_name='meta_integrations'
    )
    business_account_id = models.CharField(
        max_length=255,
        help_text="Meta Business Account ID"
    )
    page_id = models.CharField(
        max_length=255,
        help_text="Facebook/Instagram Page ID"
    )
    page_name = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Meta Page Name"
    )
    page_picture_url = models.URLField(
        blank=True,
        default='',
        max_length=1000,
        help_text="Meta Page Profile Picture URL"
    )
    access_token = models.TextField(
        editable=False,
        help_text="Meta API access token (encrypted at rest)"
    )
    access_token_expires_at = models.DateTimeField(
        help_text="When the access token expires"
    )
    verification_token = models.CharField(
        max_length=255,
        editable=False,
        help_text="Webhook verification token for Meta (encrypted at rest)"
    )
    scopes = models.JSONField(
        default=list,
        help_text="Granted Meta API scopes"
    )
    status = models.CharField(
        max_length=20,
        choices=META_INTEGRATION_STATUS_CHOICES,
        default='active',
        help_text="Integration status"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['workspace', 'business_account_id', 'page_id']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['access_token_expires_at']),
        ]
    
    def __str__(self):
        return f"{self.workspace.workspace_name} - Meta Integration ({self.status})"


class MetaLeadForm(models.Model):
    """Meta lead form configuration and mapping"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meta_integration = models.ForeignKey(
        MetaIntegration,
        on_delete=models.CASCADE,
        related_name='lead_forms'
    )
    meta_form_id = models.CharField(
        max_length=255,
        help_text="Meta Lead Form ID"
    )
    name = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Meta Lead Form Name/Title"
    )
    # REMOVED: is_active database field - now computed property
    meta_lead_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Meta Lead ID (for tracking specific leads)"
    )
    # REMOVED: The broken lead field that only stored the last lead
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['meta_integration', 'meta_form_id']
        indexes = [
            models.Index(fields=['meta_integration', 'meta_form_id']),
            models.Index(fields=['meta_lead_id']),
        ]
    
    @property
    def is_active(self) -> bool:
        """
        Form is active if it has a funnel with an active agent assigned.
        This is computed dynamically based on agent assignment.
        """
        if not hasattr(self, 'lead_funnel'):
            return False
        
        lead_funnel = self.lead_funnel
        if not lead_funnel.is_active:
            return False
            
        if not hasattr(lead_funnel, 'agent'):
            return False
            
        agent = lead_funnel.agent
        return agent.status == 'active'
    
    @property
    def workspace(self):
        """Get the workspace from the integration"""
        return self.meta_integration.workspace if self.meta_integration else None
    
    def __str__(self):
        return f"Meta Form {self.meta_form_id} - {self.meta_integration.workspace.workspace_name}"


class LeadFunnel(models.Model):
    """
    Bridge between Agent and Lead Sources
    
    This model acts as the central routing mechanism for leads.
    Each funnel is connected to a lead source (currently MetaLeadForm)
    and can be claimed by an Agent.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=255,
        help_text="Display name for this lead funnel"
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='lead_funnels',
        help_text="Workspace this funnel belongs to"
    )
    
    # Connection to Meta Lead Form (will be extended for other sources later)
    meta_lead_form = models.OneToOneField(
        'MetaLeadForm',
        on_delete=models.CASCADE,
        related_name='lead_funnel',
        null=True,
        blank=True,
        help_text="Meta lead form connected to this funnel"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this funnel should process incoming leads"
    )
    
    custom_variables = models.JSONField(
        default=list,
        blank=True,
        help_text="List of variable keys discovered from connected form questions (Meta API)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['workspace', 'is_active']),
            models.Index(fields=['workspace']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        agent_name = self.agent.name if hasattr(self, 'agent') else "Unassigned"
        return f"{self.name} (Agent: {agent_name})"
    
    @property
    def has_agent(self):
        """Check if this funnel has an assigned agent"""
        return hasattr(self, 'agent')
    
    @property
    def lead_count(self):
        """Get count of leads from this funnel"""
        return self.leads.count()


class WebhookLeadSource(models.Model):
    """
    Custom webhook source that feeds leads into a LeadFunnel.
    Authentication for inbound requests uses a Bearer token.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='webhook_lead_sources'
    )
    lead_funnel = models.OneToOneField(
        'LeadFunnel',
        on_delete=models.CASCADE,
        related_name='webhook_source',
        help_text='Lead funnel connected to this webhook source'
    )
    name = models.CharField(max_length=255, help_text='Display name for this webhook source')
    public_key = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text='Public identifier used in the inbound webhook URL'
    )
    token = models.CharField(
        max_length=128,
        help_text='Bearer token required in Authorization header'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['public_key']),
        ]
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Auto-generate public_key and token if not set
        if not self.public_key:
            # 32 chars urlsafe then stripped to 32 for URL compactness
            self.public_key = secrets.token_urlsafe(24).replace('-', '').replace('_', '')[:32]
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"WebhookLeadSource {self.name} ({self.workspace.workspace_name})"


class LeadProcessingStats(models.Model):
    """
    Track lead processing statistics for monitoring and analytics.
    Helps track how many leads are processed vs ignored.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='lead_processing_stats'
    )
    date = models.DateField(
        auto_now_add=True,
        help_text="Date of the statistics"
    )
    
    # Counters
    total_received = models.IntegerField(
        default=0,
        help_text="Total leads received from webhooks"
    )
    processed_with_agent = models.IntegerField(
        default=0,
        help_text="Leads processed with active agent"
    )
    ignored_no_funnel = models.IntegerField(
        default=0,
        help_text="Leads ignored - no funnel configured"
    )
    ignored_no_agent = models.IntegerField(
        default=0,
        help_text="Leads ignored - no agent assigned"
    )
    ignored_inactive_agent = models.IntegerField(
        default=0,
        help_text="Leads ignored - agent inactive"
    )
    ignored_inactive_funnel = models.IntegerField(
        default=0,
        help_text="Leads ignored - funnel inactive"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['workspace', 'date']
        indexes = [
            models.Index(fields=['workspace', 'date']),
            models.Index(fields=['date']),
        ]
        ordering = ['-date']
    
    @property
    def total_ignored(self):
        """Total number of ignored leads"""
        return (self.ignored_no_funnel + self.ignored_no_agent + 
                self.ignored_inactive_agent + self.ignored_inactive_funnel)
    
    @property
    def processing_rate(self):
        """Percentage of leads processed"""
        if self.total_received == 0:
            return 0
        return (self.processed_with_agent / self.total_received) * 100
    
    def __str__(self):
        return f"{self.workspace.workspace_name} - {self.date} ({self.processing_rate:.1f}% processed)"


# LiveKitAgent model removed - no longer using token authentication


## GoogleCalendarMCPAgent model removed in unified LiveKit-only flow


class CallTask(models.Model):
    """Call tasks for managing scheduled and queued calls"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Task status and management
    status = models.CharField(
        max_length=20,
        choices=CallStatus.choices,
        default=CallStatus.SCHEDULED,
        help_text="Current status of the call task"
    )
    attempts = models.IntegerField(
        default=0,
        help_text="Number of retry attempts made"
    )
    phone = models.CharField(
        max_length=20,
        help_text="Phone number to call"
    )
    
    # Optional canonical target reference for flexible routing (not used yet)
    # Examples:
    #  - "lead:<uuid>"       → stored Lead record
    #  - "test_user:<uuid>"  → user's phone for test calls
    #  - "raw_phone:+49123"  → direct E.164 dialing
    #  - "external:crm:<id>" → external system reference
    target_ref = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Canonical call target reference (e.g., 'lead:<uuid>', 'test_user:<uuid>', 'raw_phone:+49123')"
    )
    
    # Relationships
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='call_tasks',
        help_text="Workspace associated with this call task"
    )
    
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name='call_tasks',
        null=True,
        blank=True,
        help_text="Lead associated with this call task (null for test calls)"
    )
    
    # Agent assignment
    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name='call_tasks',
        help_text="Agent assigned to handle this call task"
    )
    
    
    # Scheduling
    next_call = models.DateTimeField(
        help_text="Scheduled time for the next call attempt"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Retry reason history (append-only)
    retry_reasons = models.JSONField(default=list, help_text="Append-only list of retry reason dicts: {reason, hint, at}")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'next_call']),
            models.Index(fields=['agent', 'status']),
            models.Index(fields=['next_call']),
        ]
    
    def __str__(self):
        return f"CallTask {self.id} - {self.workspace.name} - {self.agent.name} ({self.status})"
    
    def increment_retries(self, max_retries=10):
        """Increment the retry counter with safety limit"""
        if self.attempts < max_retries:
            self.attempts += 1
            self.save(update_fields=['attempts'])
        else:
            # Max retries reached - delete CallTask immediately
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"CallTask {self.id} deleted - max retries ({max_retries}) reached")
            self.delete()
    
    def can_retry(self, max_retries=3):
        """Check if the task can be retried"""
        return self.attempts < max_retries and self.status in [CallStatus.SCHEDULED, CallStatus.RETRY]


# Signal handlers for eager FeatureUsage initialization
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=WorkspaceSubscription)
def initialize_subscription_usage(sender, instance, created, **kwargs):
    """
    Auto-initialize FeatureUsage records when WorkspaceSubscription is created via Stripe.
    This ensures all features in the plan have usage records from the start.
    """
    # Only initialize for Stripe-created subscriptions (not superuser Enterprise plans)
    # We check if workspace has stripe_customer_id to distinguish Stripe vs manual subscriptions
    if created and instance.is_active and instance.workspace.stripe_customer_id:
        # Avoid circular imports by importing here
        from core.quotas import initialize_feature_usage_for_subscription

        try:
            initialize_feature_usage_for_subscription(instance)
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Initialized FeatureUsage records for Stripe subscription: %s", instance)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Failed to initialize FeatureUsage for subscription %s: %s", instance, str(e))
    
