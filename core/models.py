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
    
    # Password reset fields
    password_reset_token = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Token for password reset"
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
            expiry_time = self.password_reset_sent_at + timezone.timedelta(hours=24)
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
    
    # Subscription
    current_plan = models.ForeignKey(
        'Plan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workspaces',
        help_text="Current subscription plan"
    )
    subscription_status = models.CharField(
        max_length=20,
        choices=[
            ('trial', 'Trial'),
            ('active', 'Active'),
            ('cancelled', 'Cancelled'),
            ('past_due', 'Past Due'),
            ('unpaid', 'Unpaid'),
        ],
        default='trial',
        help_text="Current subscription status"
    )
    
    # Stripe integration
    stripe_customer_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        unique=True,
        help_text="Stripe Customer ID for billing"
    )
    stripe_subscription_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Current Stripe Subscription ID (sub_xxx)"
    )
    
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
    max_retries = models.IntegerField(
        help_text="Maximum number of retry attempts for calls",
        default=3
    )
    workdays = models.JSONField(
        default=list,
        help_text="List of working days, e.g., ['monday', 'tuesday', 'wednesday']"
    )
    call_from = models.TimeField(help_text="Start time for calls")
    call_to = models.TimeField(help_text="End time for calls")
    character = models.TextField(help_text="Agent character/personality description")
    prompt = models.TextField(
        help_text="Agent prompt/instructions for AI behavior",
        blank=True
    )
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


class GoogleCalendarConnection(models.Model):
    """Google OAuth connection and API credentials"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'User', 
        on_delete=models.CASCADE, 
        related_name='google_calendar_connections'
    )
    workspace = models.ForeignKey(
        'Workspace', 
        on_delete=models.CASCADE, 
        related_name='google_calendar_connections'
    )
    
    # Google OAuth fields
    account_email = models.EmailField(help_text="Google account email")
    refresh_token = models.TextField(help_text="OAuth refresh token")
    access_token = models.TextField(help_text="OAuth access token")
    token_expires_at = models.DateTimeField(help_text="When access token expires")
    scopes = models.JSONField(
        default=list,
        help_text="Granted OAuth scopes"
    )
    
    # Connection status
    active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    sync_errors = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['workspace', 'account_email']
        indexes = [
            models.Index(fields=['workspace', 'active']),
            models.Index(fields=['token_expires_at']),
        ]
    
    def __str__(self):
        return f"{self.workspace.workspace_name} - {self.account_email}"


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
            ('outlook', 'Microsoft Outlook'),
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
    
    def __str__(self):
        return f"{self.workspace.workspace_name} - {self.name} ({self.provider})"


class GoogleCalendar(models.Model):
    """Google-specific calendar metadata"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.OneToOneField(
        'Calendar', 
        on_delete=models.CASCADE, 
        related_name='google_calendar'
    )
    # Google Calendar API fields
    external_id = models.CharField(
        max_length=255, 
        unique=True,
        help_text="Google Calendar ID"
    )
    # Calendar properties
    primary = models.BooleanField(default=False)
    time_zone = models.CharField(max_length=50)
    
    refresh_token = models.CharField(max_length=255, help_text="Google Calendar API refresh token")
    access_token = models.CharField(max_length=255, help_text="Google Calendar API access token")
    token_expires_at = models.DateTimeField(help_text="When access token expires")
    scopes = models.JSONField(
        default=list,
        help_text="Granted OAuth scopes"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.calendar.name} ({self.external_id})"


class CalendarConfiguration(models.Model):
    """Configuration settings for calendar scheduling"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.ForeignKey(
        'Calendar', 
        on_delete=models.CASCADE, 
        related_name='configurations'
    )
    
    # Scheduling settings
    duration = models.IntegerField(help_text="Duration of appointments in minutes")
    prep_time = models.IntegerField(help_text="Preparation time in minutes before appointments")
    days_buffer = models.IntegerField(
        default=0,
        help_text="Days buffer for scheduling (0 = same day)"
    )
    from_time = models.TimeField(help_text="Start time for scheduling availability")
    to_time = models.TimeField(help_text="End time for scheduling availability")
    workdays = models.JSONField(
        default=list,
        help_text="List of working days, e.g., ['monday', 'tuesday', 'wednesday']"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Config for {self.calendar.name} - {self.duration}min"
