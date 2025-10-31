import secrets
import uuid

from django.db import models

from .workspace_models import Workspace


class Lead(models.Model):
    """Model for leads"""

    # Choices
    INTEGRATION_PROVIDER_CHOICES = [
        ("meta", "Meta (Facebook/Instagram)"),
        ("google", "Google"),
        ("manual", "Manual Entry"),
        ("custom-webhook", "Custom Webhook"),
        ("csv", "CSV File"),
    ]

    # Fields
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(
        max_length=255,
    )
    surname = models.CharField(
        max_length=255,
    )
    email = models.EmailField(
        max_length=255,
    )
    phone_number = models.CharField(
        max_length=50,
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="leads",
        blank=True,
        help_text="Workspace the lead belongs to",
    )
    integration_provider = models.CharField(
        max_length=20,
        choices=INTEGRATION_PROVIDER_CHOICES,
        null=True,
        blank=True,
        help_text="Integration provider source",
    )
    variables = models.JSONField(
        default=dict,
        help_text="Additional variables related to the lead",
    )

    lead_funnel = models.ForeignKey(
        "LeadFunnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        help_text="Source funnel this lead came from",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    meta_data = models.JSONField(
        default=dict,
        help_text="Error Messages and additional metadata related to the lead",
    )

    @property
    def full_name(self):
        return f"{self.name} {self.surname}"

    class Meta:
        verbose_name = "Lead"
        verbose_name_plural = "Leads"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Lead: {self.full_name}, Phone Number: {self.phone_number}, Workspace: {self.workspace.workspace_name}"


class LeadFunnel(models.Model):
    """
    Model for lead funnels.
    Lead funnels are bridges between agents and lead sources.
    Each funnel is connected to a lead source and can be claimed by an Agent.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(
        max_length=255,
        help_text="Display name for this lead funnel",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="lead_funnels",
        help_text="Workspace this funnel belongs to",
    )
    meta_lead_form = models.OneToOneField(
        "MetaLeadForm",
        on_delete=models.CASCADE,
        related_name="lead_funnel",
        null=True,
        blank=True,
        help_text="Meta lead form connected to this funnel",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Does the funnel process leads",
    )
    custom_variables = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Variable keys coming from the respective lead source",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def has_agent(self):
        """Check if this funnel has an assigned agent"""
        return hasattr(self, "agent")

    @property
    def lead_count(self):
        """Get count of leads from this funnel"""
        return self.leads.count()

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "is_active"]),
            models.Index(fields=["workspace"]),
            models.Index(fields=["is_active"]),
        ]
        verbose_name = "Lead funnel"
        verbose_name_plural = "Lead funnels"
        ordering = ["-created_at"]

    def __str__(self):
        agent_name = self.agent.name if hasattr(self, "agent") else "Unassigned"
        return f"{self.name}, active: {self.is_active}, Agent: {agent_name}"


class WebhookLeadSource(models.Model):
    """
    Lead source via custom webhook.
    Authentication via bearer token.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(
        max_length=255, help_text="Display name for this webhook source"
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="webhook_lead_sources",
    )
    lead_funnel = models.OneToOneField(
        "LeadFunnel",
        on_delete=models.CASCADE,
        related_name="webhook_source",
        help_text="Lead funnel connected to this webhook source",
    )
    public_key = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Public identifier used in the inbound webhook URL",
    )
    token = models.CharField(
        max_length=128,
        help_text="Bearer token required in Authorization header",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["public_key"]),
        ]
        verbose_name = "Webhook lead source"
        verbose_name_plural = "Webhook lead sources"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}, Workspace: {self.workspace.workspace_name}"

    def save(self, *args, **kwargs):
        if not self.public_key:
            self.public_key = (
                secrets.token_urlsafe(32).replace("-", "").replace("_", "")[:32]
            )
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

