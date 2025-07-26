from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class EmailBackend(BaseBackend):
    """
    Custom authentication backend that uses email instead of username
    and enforces email verification.
    """
    
    def authenticate(self, request, email=None, password=None, **kwargs):
        """
        Authenticate user using email and password.
        Only allows login if email is verified.
        """
        if email is None or password is None:
            return None
        
        try:
            # Find user by email
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a nonexistent user
            User().set_password(password)
            return None
        
        # Check password
        if user.check_password(password):
            # Only allow login if email is verified
            if user.is_email_verified and user.can_login():
                return user
        
        return None
    
    def get_user(self, user_id):
        """Get user by ID for session authentication"""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class EmailOrUsernameBackend(BaseBackend):
    """
    Authentication backend that allows login with either email or username.
    This is useful for backward compatibility during migration.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user using email or username and password.
        Enforces email verification.
        """
        if username is None or password is None:
            return None
        
        try:
            # Try to find user by email first, then by username
            user = User.objects.get(
                Q(email=username) | Q(username=username) if hasattr(User, 'username') else Q(email=username)
            )
        except User.DoesNotExist:
            # Run the default password hasher once to reduce timing attacks
            User().set_password(password)
            return None
        
        # Check password
        if user.check_password(password):
            # Only allow login if email is verified
            if user.is_email_verified and user.can_login():
                return user
        
        return None
    
    def get_user(self, user_id):
        """Get user by ID for session authentication"""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None 