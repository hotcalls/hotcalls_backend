import uuid

from django.db import models

from .workspace_models import WorkspaceUsage


class Plan(models.Model):
    """Model for subscription plans"""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name of the plan",
    )
    features = models.ManyToManyField(
        "Feature",
        through="PlanFeature",
        related_name="mapping_plan_features",
    )

    # Stripe integration fields
    stripe_product_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text="Stripe Product ID (prod_xxx)",
    )
    stripe_price_id_monthly = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Stripe Price ID for monthly billing (price_xxx)",
    )
    price_monthly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monthly price in EUR",
    )

    is_active = models.BooleanField(
        default=True, help_text="Is this plan available for new subscriptions?"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Plans"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.plan_name}. Monthly price: {self.price_monthly}. Features: {self.features}"


class Feature(models.Model):
    """
    Model for features.
    Features can be assigned to plans and have different units to be checked and expanded upon
    """

    # Choices
    FEATURE_UNIT_CHOICES = [
        ("minute", "Minute"),
        ("general_unit", "General Unit"),
        ("access", "Access"),
        ("request", "Request"),
        ("gb", "Gigabyte"),
    ]

    # Fields
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    feature_name = models.CharField(
        max_length=100,
        unique=True,
    )
    description = models.TextField(
        blank=True,
        help_text="Feature description",
    )
    unit = models.CharField(
        max_length=20,
        choices=FEATURE_UNIT_CHOICES,
        blank=True,
        null=True,
        help_text="Unit type for this feature",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Feature"
        verbose_name_plural = "Features"
        ordering = ["created_at"]

    def __str__(self):
        return self.feature_name


class EndpointFeature(models.Model):
    """
    Outdated model that maps an API route to the feature.
    Used in outdated middleware meant for tracking and enforcing quotas
    TODO: Remove together with middleware.
    """

    # Choices
    HTTP_METHOD_CHOICES = [
        ("*", "ANY"),
        ("GET", "GET"),
        ("POST", "POST"),
        ("PUT", "PUT"),
        ("PATCH", "PATCH"),
        ("DELETE", "DELETE"),
        ("HEAD", "HEAD"),
        ("OPTIONS", "OPTIONS"),
    ]

    # Fields
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
        related_name="endpoint_features",
        help_text="Feature that governs this endpoint",
    )
    route_name = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Django route name or regex pattern for the endpoint",
    )
    http_method = models.CharField(
        max_length=10,
        choices=HTTP_METHOD_CHOICES,
        default=HTTP_METHOD_CHOICES[0][0],
        help_text="HTTP method (GET, POST, etc.) or '*' for any method",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["route_name", "http_method"],
                name="route_name_http_method_unique",
            )
        ]
        indexes = [
            models.Index(fields=["route_name"]),
            models.Index(fields=["route_name", "http_method"]),
        ]
        verbose_name = "EndpointFeature"
        verbose_name_plural = "EndpointFeatures"
        ordering = ["created_at"]

    def __str__(self):
        method_str = f" ({self.http_method})" if self.http_method else ""
        return f"{self.route_name}{method_str} → {self.feature.feature_name}"


class PlanFeature(models.Model):
    """Mapping table between Plan and Feature with limit"""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
    )
    limit = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        help_text="Feature limit for this plan",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraint = [
            models.UniqueConstraint(
                fields=["plan", "feature"],
                name="unique_feature_per_plan",
            )
        ]
        verbose_name = "PlanFeature"
        verbose_name_plural = "PlanFeatures"
        ordering = ["created_at"]

    def __str__(self):
        return (
            f"{self.plan.plan_name} - {self.feature.feature_name} (limit: {self.limit})"
        )


class FeatureUsage(models.Model):
    """
    Counter per feature inside a WorkspaceUsage container.
    used_amount is:
      • minutes   for unit='minute'
      • integer   for unit='general_unit' or 'access' (0 or 1)
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    usage_record = models.ForeignKey(
        WorkspaceUsage,
        related_name="feature_usages",
        on_delete=models.CASCADE,
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
    )
    used_amount = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        default=0,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def limit(self):
        """
        Retrieve feature limit.
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usage_record", "feature"],
                name="unique_usage_record_per_feature",
            )
        ]
        verbose_name = "FeatureUsage"
        verbose_name_plural = "FeatureUsages"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.feature.feature_name} - {self.used_amount}"
