import uuid

from django.db import models

from .workspace_models import Workspace
from .lead_models import LeadFunnel


class MetaIntegration(models.Model):
    """
    Meta integration for workspaces.
    """

    # Choices
    META_INTEGRATION_STATUS_CHOICES = [
        ("active", "Active"),
        ("expired", "Expired"),
        ("revoked", "Revoked"),
        ("error", "Error"),
        ("disconnected", "Disconnected"),
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
        related_name="meta_integrations",
    )
    business_account_id = models.CharField(
        max_length=255,
        help_text="Meta Business Account ID",
    )
    page_id = models.CharField(
        max_length=255,
        help_text="Facebook/Instagram Page ID",
    )
    page_name = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Meta Page Name",
    )
    page_picture_url = models.URLField(
        blank=True,
        default="",
        max_length=1000,
        help_text="Meta Page Profile Picture URL",
    )
    access_token = models.TextField(
        editable=False,
        help_text="Meta API access token",
    )
    access_token_expires_at = models.DateTimeField(
        help_text="When the access token expires"
    )
    verification_token = models.CharField(
        max_length=255,
        editable=False,
        help_text="Webhook verification token for Meta",
    )
    scopes = models.JSONField(
        default=list,
        help_text="Granted Meta API scopes",
    )
    status = models.CharField(
        max_length=20,
        choices=META_INTEGRATION_STATUS_CHOICES,
        default="active",
        help_text="Integration status",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "business_account_id", "page_id"],
            )
        ]
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["access_token_expires_at"]),
        ]
        verbose_name = "Meta integration"
        verbose_name_plural = "Meta integrations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Meta Integration in workspace {self.workspace.workspace_name}, status: {self.status}"


class MetaLeadForm(models.Model):
    """
    Meta lead form configuration and mapping.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    meta_integration = models.ForeignKey(
        MetaIntegration,
        on_delete=models.CASCADE,
        related_name="lead_forms",
    )
    meta_form_id = models.CharField(
        max_length=255,
        help_text="Meta Lead Form ID",
    )
    name = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Meta Lead Form Name/Title",
    )
    meta_lead_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Meta Lead ID",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_active(self) -> bool:
        """
        Activity based on having active agent and lead funnel.
        """
        if not hasattr(self, "lead_funnel"):
            return False

        lead_funnel = self.lead_funnel
        if not lead_funnel.is_active:
            return False

        if not hasattr(lead_funnel, "agent"):
            return False

        agent = lead_funnel.agent
        return agent.status == "active"

    @property
    def workspace(self):
        """Get the workspace from the integration"""
        return self.meta_integration.workspace if self.meta_integration else None

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["meta_integration", "meta_form_id"],
            )
        ]
        indexes = [
            models.Index(fields=["meta_integration", "meta_form_id"]),
            models.Index(fields=["meta_lead_id"]),
        ]
        verbose_name = "Meta lead form"
        verbose_name_plural = "Meta lead forms"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Meta Form {self.meta_form_id} - {self.meta_integration.workspace.workspace_name}"
