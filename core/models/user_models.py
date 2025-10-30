"""
Models for User Logic
"""

import datetime
import logging
import secrets
import uuid

from core.services.phone_assignment import (
    WorkspacePhoneAssignmentError,
    assign_default_number_to_workspace,
)
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone

from .workspace_models import Workspace

logger = logging.getLogger(__name__)


class CustomUserManager(BaseUserManager):
    """Custom manager for user model. works with email-based login"""

    def create_user(self, email, password, **extra_fields):
        """Create and return new user."""
        if not email:
            raise ValueError("The Email field must be set")
        if not password:
            raise ValueError("The Password field must be set")

        email = self.normalize_email(email)

        extra_fields.setdefault("status", "active")

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password, **extra_fields):
        """Create and return a superuser with an email and password"""
        if not email:
            raise ValueError("The Email field must be set")
        if not password:
            raise ValueError("The Password field must be set")

        # Superuser is always superuser, staff, active, email_verified
        extra_fields["is_superuser"] = True
        extra_fields["is_staff"] = True
        extra_fields["status"] = "active"
        extra_fields["is_email_verified"] = True

        user = self.create_user(email, password, **extra_fields)

        # Create workspace for superuser
        self._setup_superuser_workspace_and_plan(user)

        return user

    def _setup_superuser_workspace_and_plan(self, user):
        """Setup workspace for superuser"""

        try:
            workspace = Workspace.objects.create(
                workspace_name=f"Admin Workspace {user.full_name}",
            )

            workspace.users.add(user)

            # Auto-assign a global phone number to workspace. Non-critical if fail
            try:
                assign_default_number_to_workspace(workspace)
            except WorkspacePhoneAssignmentError as e:
                logger.error(
                    f"Failed to assign phone number to super user workspace {workspace.workspace_name}: {str(e)}"
                )
                pass
            except Exception as e:
                logger.error(
                    f"Unexpected Exception while assigning phone number to super user workspace {workspace.workspace_name}: {str(e)}"
                )
                pass

        except Exception as e:
            logger.error(
                f"Failed to setup workspace/plan for superuser {user.email}: {str(e)}"
            )


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model with email"""

    USER_STATUS_CHOICES = [
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("forever_disabled", "Forever Disabled"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # User information fields
    email = models.EmailField(
        unique=True,
        help_text="Email address used for login"
    )
    first_name = models.CharField(
        max_length=150,
        help_text="User first name"
    )
    last_name = models.CharField(
        max_length=150,
        help_text="User last name"
    )
    phone = models.CharField(
        max_length=50,
        unique=True,
        help_text="User phone number. Unique",
    )
    status = models.CharField(
        max_length=20,
        choices=USER_STATUS_CHOICES,
        default="active",
        help_text="User account status",
    )
    is_staff = models.BooleanField(
        default=False, help_text="Can User access admin site"
    )
    has_used_trial = models.BooleanField(
        default=False,
        help_text="Whether this user has ever used a trial period (lifetime limit)",
    )
    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe customer ID for billing",
    )

    # Verification fields
    is_email_verified = models.BooleanField(
        default=False,
        help_text="Has the user email been verified?"
    )
    email_verification_token = models.CharField(
        max_length=100,
        blank=True,
        editable=False,
        help_text="Token used for email verification",
    )
    email_verification_sent_at = models.DateTimeField(
        blank=True,
        help_text="When email verification was sent"
    )
    password_reset_token = models.CharField(
        max_length=100,
        blank=True,
        editable=False,
        help_text="Token for password reset",
    )
    password_reset_sent_at = models.DateTimeField(
        blank=True,
        help_text="When password reset email was sent "
    )

    # Timestamps
    date_joined = models.DateTimeField(
        default=timezone.now,
        help_text="When the user account was created"
    )
    last_login = models.DateTimeField(
        blank=True,
        help_text="When the user last logged in"
    )

    # User django configuration
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = CustomUserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self):
        return f"({self.email}), {self.full_name}, created at {self.date_joined}.\nStatus: {self.status}\nUsed Trial Period: {self.has_used_trial}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def generate_email_verification_token(self):
        """Generate a new email verification token"""
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = timezone.now()
        self.save(
            update_fields=["email_verification_token", "email_verification_sent_at"]
        )
        return self.email_verification_token

    def verify_email(self, token):
        """Verify email with the provided token"""
        if self.email_verification_token == token and self.email_verification_token:
            self.is_email_verified = True
            self.email_verification_token = None
            self.email_verification_sent_at = None
            self.save(
                update_fields=[
                    "is_email_verified",
                    "email_verification_token",
                    "email_verification_sent_at",
                ]
            )
            return True
        return False

    def generate_password_reset_token(self):
        """Generate a new password reset token"""
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_sent_at = timezone.now()
        self.save(update_fields=["password_reset_token", "password_reset_sent_at"])
        return self.password_reset_token

    def verify_password_reset_token(self, token):
        """Verify password reset token and check if it's still valid (24 hours)"""
        if not self.password_reset_token or self.password_reset_token != token:
            return False

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
            self.save(
                update_fields=[
                    "password",
                    "password_reset_token",
                    "password_reset_sent_at",
                ]
            )
            return True
        return False

    def can_login(self):
        """Check if user can login (active and email verified)"""
        return self.is_email_verified and self.status == "active"
