from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import uuid
from django.utils import timezone
import secrets


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

CALL_STATUS_CHOICES = [
    ('appointment_scheduled', 'Appointment Scheduled'),
    ('not_reached', 'Not Reached'),
    ('no_interest', 'No Interest'),
    ('reached', 'Reached'),
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

CALENDAR_TYPE_CHOICES = [
    ('google', 'Google'),
    ('outlook', 'Outlook'),
]


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
        
        return self.create_user(email, password, **extra_fields)


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
        help_text="Token for email verification"
    )
    email_verification_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the verification email was last sent"
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.provider}: {self.voice_external_id}"





class Plan(models.Model):
    """Subscription plans"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan_name = models.CharField(max_length=100, unique=True)
    features = models.ManyToManyField('Feature', through='PlanFeature', related_name='mapping_plan_features')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.plan_name


class Feature(models.Model):
    """High-level features that can be assigned to plans"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, help_text="Feature description")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.feature_name


class PlanFeature(models.Model):
    """Mapping table between Plan and Feature with limit"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
    limit = models.IntegerField(help_text="Feature limit for this plan")
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.workspace_name


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
    greeting_inbound = models.TextField(help_text="Greeting for inbound calls")
    greeting_outbound = models.TextField(help_text="Greeting for outbound calls")
    
    # UPDATED: Voice as relationship to Voice model
    voice = models.ForeignKey(
        Voice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mapping_voice_agents',
        help_text="Voice configuration for this agent"
    )
    
    language = models.CharField(max_length=50, help_text="Agent language")
    retry_interval = models.IntegerField(
        help_text="Retry interval in minutes",
        default=30
    )
    workdays = models.JSONField(
        default=list,
        help_text="List of working days, e.g., ['monday', 'tuesday', 'wednesday']"
    )
    call_from = models.TimeField(help_text="Start time for calls")
    call_to = models.TimeField(help_text="End time for calls")
    character = models.TextField(help_text="Agent character/personality description")
    config_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Configuration ID for agent settings"
    )
    phone_numbers = models.ManyToManyField('PhoneNumber', related_name='mapping_agent_phonenumbers', blank=True)
    calendar_configuration = models.ForeignKey(
        'CalendarConfiguration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mapping_config_agents',
        help_text="Calendar configuration for this agent"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.workspace.workspace_name})"


class PhoneNumber(models.Model):
    """Phone numbers that can be shared across multiple agents"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phonenumber = models.CharField(
        max_length=17,
        unique=True,
        help_text="Phone number"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.phonenumber


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
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='mapping_lead_calllogs')
    agent = models.ForeignKey(
        Agent, 
        on_delete=models.CASCADE, 
        related_name='mapping_agent_calllogs',
        help_text="Agent who made/received the call"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    from_number = models.CharField(max_length=20, help_text="Caller's phone number")
    to_number = models.CharField(max_length=20, help_text="Recipient's phone number")
    duration = models.IntegerField(help_text="Call duration in seconds")
    disconnection_reason = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        help_text="Reason for call disconnection"
    )
    direction = models.CharField(
        max_length=10, 
        choices=CALL_DIRECTION_CHOICES, 
        help_text="Call direction"
    )
    status = models.CharField(
        max_length=25,
        choices=CALL_STATUS_CHOICES,
        null=True,
        blank=True,
        help_text="Call outcome status"
    )
    appointment_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Scheduled appointment datetime when status is 'terminvereinbart'"
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Call: {self.from_number} → {self.to_number} ({self.timestamp})"


class Calendar(models.Model):
    """Calendar integration for scheduling"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace, 
        on_delete=models.CASCADE, 
        related_name='mapping_workspace_calendars',
        null=True,
        blank=True
    )
    calendar_type = models.CharField(
        max_length=20,
        choices=CALENDAR_TYPE_CHOICES,
        help_text="Calendar provider type",
        default="google"
    )
    account_id = models.CharField(
        max_length=255,
        help_text="Account ID for the calendar service",
        default="default@calendar.com"
    )
    auth_token = models.TextField(
        help_text="Authentication token for calendar access",
        default="default_token"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['workspace', 'calendar_type', 'account_id']
    
    def __str__(self):
        return f"{self.workspace.workspace_name} - {self.calendar_type.title()} ({self.account_id})"


class CalendarConfiguration(models.Model):
    """Configuration settings for calendar scheduling"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.ForeignKey(
        Calendar, 
        on_delete=models.CASCADE, 
        related_name='mapping_calendar_configurations'
    )
    sub_calendar_id = models.CharField(
        max_length=255,
        help_text="Google subcalendar or actual calendar ID",
        default="primary"
    )
    duration = models.IntegerField(
        help_text="Duration of appointments in minutes",
        default=30
    )
    prep_time = models.IntegerField(
        help_text="Preparation time in minutes before appointments",
        default=5
    )
    days_buffer = models.IntegerField(
        default=0,
        help_text="Days buffer for scheduling (0 = same day)"
    )
    from_time = models.TimeField(
        help_text="Start time for scheduling availability",
        default="09:00:00"
    )
    to_time = models.TimeField(
        help_text="End time for scheduling availability", 
        default="17:00:00"
    )
    workdays = models.JSONField(
        default=list,
        help_text="List of working days, e.g., ['monday', 'tuesday', 'wednesday']"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Config for {self.calendar} - {self.sub_calendar_id}"
