"""
Models for Workspace Logic
"""

import datetime
import secrets
import uuid

from django.db import models
from django.utils import timezone

from .plan_models import Plan
from .user_models import User
from .telephony_models import PhoneNumber


class Workspace(models.Model):
    """Workspace model"""

    # Choices
    SUBSCRIPTION_STATUS_CHOICES = [
        ("none", "None"),
        ("trial", "Trial"),
        ("active", "Active"),
        ("past_due", "Past Due"),
        ("unpaid", "Unpaid"),
        ("cancelled", "Cancelled"),
    ]

    # Fields
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    workspace_name = models.CharField(max_length=255)
    users = models.ManyToManyField(
        User,
        related_name="member_workspaces",
    )
    # Ownership and administration
    creator = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_workspaces",
    )
    admin_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_workspaces",
    )

    # Stripe integration
    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Stripe Customer ID for billing",
    )
    stripe_subscription_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Current Stripe Subscription ID",
    )

    subscription_status = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_STATUS_CHOICES,
        default="none",
        help_text="Current subscription status",
    )

    smtp_enabled = models.BooleanField(
        default=False,
        help_text="Enable outbound email via this workspace SMTP configuration",
    )
    smtp_host = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="SMTP hostname",
    )
    smtp_port = models.IntegerField(
        default=587,
        help_text="SMTP port",
    )
    smtp_use_tls = models.BooleanField(
        default=True,
        help_text="Use STARTTLS",
    )
    smtp_use_ssl = models.BooleanField(
        default=False,
        help_text="Use implicit SSL/TLS",
    )
    smtp_username = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="SMTP username",
    )
    smtp_password_encrypted = models.TextField(
        blank=True,
        default="",
        help_text="SMTP password (encrypted at rest)",
    )
    smtp_from_email = models.EmailField(
        blank=True,
        default="",
        help_text="Sender email address for outbound messages",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def current_subscription(self):
        """Get current active subscription"""
        try:
            return self.workspacesubscription.get(is_active=True)
        except WorkspaceSubscription.DoesNotExist:
            return None

    class Meta:
        constraints = [
            # Ensure unique stripe_customer_id when not NULL
            models.UniqueConstraint(
                fields=["stripe_customer_id"],
                condition=models.Q(stripe_customer_id__isnull=False),
                name="unique_stripe_customer_id",
            ),
            # Ensure unique stripe_subscription_id when not NULL
            models.UniqueConstraint(
                fields=["stripe_subscription_id"],
                condition=models.Q(stripe_subscription_id__isnull=False),
                name="unique_stripe_subscription_id",
            ),
        ]
        verbose_name = "Workspace"
        verbose_name_plural = "Workspaces"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.workspace_name} created at {self.created_at}."

    def is_admin(self, user: "User") -> bool:
        if user is None:
            return False
        return bool(self.admin_user and self.admin_user_id == user.id)


class WorkspaceInvitation(models.Model):
    """Workspace Invitation model per email"""

    # Choices
    INVITATION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    ]

    # Fields
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="invitations",
        help_text="Workspace the user is being invited to",
    )
    email = models.EmailField(
        help_text="Email address of the person being invited",
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_invitations",
        help_text="User who sent the invitation",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Secure token for invitation acceptance (encrypted at rest)",
    )
    status = models.CharField(
        max_length=20,
        choices=INVITATION_STATUS_CHOICES,
        default="pending",
        help_text="Current status of the invitation",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="When this invitation expires (7 days from creation)"
    )
    accepted_at = models.DateTimeField(
        null=True, blank=True, help_text="When the invitation was accepted"
    )

    class Meta:
        constraints = [
            # Only one pending invitation per workspace-email combination
            models.UniqueConstraint(
                fields=["workspace", "email"],
                condition=models.Q(status="pending"),
                name="unique_pending_invitation_per_workspace_email",
            )
        ]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["email", "status"]),
            models.Index(fields=["workspace", "status"]),
        ]
        verbose_name = "Workspace invitation"
        verbose_name_plural = "Workspace invitations"
        ordering = ["created_at"]

    def __str__(self):
        return f"Invitation: From {self.invited_by} to {self.email} into {self.workspace.workspace_name}. Status: ({self.status})"

    def save(self, *args, **kwargs):
        # Set expiration to 7 days from now if not set
        if not self.expires_at:
            self.expires_at = timezone.now() + datetime.timedelta(days=7)

        # Generate token if not set
        if not self.token:
            self.token = self.generate_token()

        super().save(*args, **kwargs)

    @staticmethod
    def generate_token():
        """Generate a secure random token for invitations"""
        return secrets.token_urlsafe(32)

    def is_valid(self):
        """Check if invitation is still valid"""
        return (
            self.status == "pending"
            and self.expires_at
            and timezone.now() < self.expires_at
        )

    def accept(self, user):
        """Accept the invitation and add user to workspace"""
        if not self.is_valid():
            raise ValueError("Invitation is not valid or has expired")

        if user.email != self.email:
            raise ValueError("Email address does not match invitation")

        # TODO: Maybe extract this logic of adding user to workspace to service layer.
        # Add user to workspace
        self.workspace.users.add(user)

        # Update invitation status
        self.status = "accepted"
        self.accepted_at = timezone.now()
        self.save(update_fields=["status", "accepted_at"])

        return True

    def cancel(self):
        """Cancel the invitation"""
        if self.status == "pending":
            self.status = "cancelled"
            self.save(update_fields=["status"])


class WorkspaceSubscription(models.Model):
    """
    Makes the relationship between a Workspace and a Plan explicit,
    and captures periods so you can keep historical data.
    TODO: Check what this means and maybe change logic.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="workspacesubscription",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="workspacesubscriptionplan",
    )
    started_at = models.DateTimeField()
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # One active subscription at a time
        constraints = [
            models.UniqueConstraint(
                fields=["workspace"],
                condition=models.Q(is_active=True),
                name="unique_active_subscription_per_workspace",
            )
        ]
        verbose_name = "Workspace subscription"
        verbose_name_plural = "Workspace subscriptions"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.workspace.workspace_name} - {self.plan.plan_name}. Status: ({'Active' if self.is_active else 'Inactive'})"


class WorkspaceUsage(models.Model):
    """
    One record per workspace **per billing period**.
    Historical rows are never mutated – new row each period.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="workspaceusages",
    )
    subscription = models.ForeignKey(
        WorkspaceSubscription,
        on_delete=models.PROTECT,
        related_name="workspaceusagesubscription",
        help_text="Subscription that was active for this usage period",
    )
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    # Extra purchased call minutes for the current billing period
    extra_call_minutes = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        default=0,
        help_text="Extra purchased call minutes credited to this billing period",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "period_start", "period_end"],
                name="unique_active_usage_per_workspace",
            )
        ]
        verbose_name = "Workspace usage"
        verbose_name_plural = "Workspaces usage"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.workspace}, period from {self.period_start:%Y-%m-%d} to {self.period_end:%Y-%m-%d}. Extra call minutes: {self.extra_call_minutes}"


class WorkspacePhoneNumber(models.Model):
    """
    Model to map workspaces to phone numbers with a default number.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    workspace = models.ForeignKey(
        "Workspace",
        on_delete=models.CASCADE,
        related_name="workspace_phonenumbers",
        help_text="Workspace that can use this phone number",
    )
    phone_number = models.ForeignKey(
        PhoneNumber,
        on_delete=models.CASCADE,
        related_name="workspace_mappings",
        help_text="Phone number available to this workspace",
    )
    is_default = models.BooleanField(
        default=False, help_text="If true, default phone number for this workspace"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "phone_number"],
                name="unique_workspace_phone_number",
            ),
        ]
        verbose_name = "Workspace phone number"
        verbose_name_plural = "Workspaces phone numbers"
        ordering = ["created_at"]

    def __str__(self):
        return f"Workspace: {self.workspace.workspace_name}, Phone number: {self.phone_number.phone_number}. {'default' if self.is_default else 'pool'}"
