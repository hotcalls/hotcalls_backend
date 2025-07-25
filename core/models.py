from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid


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

SOCIAL_PROVIDER_CHOICES = [
    ('google', 'Google'),
    ('apple', 'Apple'),
    ('facebook', 'Facebook'),
]


class User(AbstractUser):
    """Custom User model extending Django's AbstractUser"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(
        max_length=50,
        help_text="Phone number in international format"
    )
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
    
    def __str__(self):
        return f"{self.username} ({self.email})"


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
    greeting = models.TextField(help_text="Agent greeting message")
    voice = models.CharField(max_length=255, help_text="Voice setting for the agent")
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Agent for {self.workspace.workspace_name}"


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
        return f"Blacklist: {self.user.username} ({self.status})"


class CallLog(models.Model):
    """Call logs for tracking all calls"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='mapping_lead_calllogs')
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
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Call: {self.from_number} → {self.to_number} ({self.timestamp})"
