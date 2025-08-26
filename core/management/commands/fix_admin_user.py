"""
Management command to verify and fix admin user authentication issues.
This command helps diagnose and fix login problems for admin users.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate

User = get_user_model()


class Command(BaseCommand):
    help = 'Verify and fix admin user authentication settings'

    def add_arguments(self, parser):
        parser.add_argument(
            'email',
            type=str,
            help='Email address of the admin user to check/fix'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Automatically fix issues found (set is_email_verified=True, is_active=True, status=active, is_staff=True)'
        )
        parser.add_argument(
            '--set-password',
            type=str,
            help='Set a new password for the user'
        )
        parser.add_argument(
            '--test-login',
            type=str,
            help='Test login with the provided password'
        )

    def handle(self, *args, **options):
        email = options['email']
        
        try:
            user = User.objects.get(email=email)
            self.stdout.write(f"\n✓ User found: {user.email}")
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"\n✗ User with email '{email}' not found"))
            return

        # Display current status
        self.stdout.write("\nCurrent User Status:")
        self.stdout.write("-" * 50)
        
        status_checks = [
            ('Email', user.email, True),
            ('Is Active', user.is_active, user.is_active),
            ('Is Staff', user.is_staff, user.is_staff),
            ('Is Superuser', user.is_superuser, None),  # Info only
            ('Email Verified', user.is_email_verified, user.is_email_verified),
            ('Account Status', user.status, user.status == 'active'),
            ('Has Password', user.has_usable_password(), user.has_usable_password()),
        ]
        
        issues_found = []
        
        for field, value, is_ok in status_checks:
            if is_ok is None:  # Info only field
                self.stdout.write(f"  {field:20} : {value}")
            elif is_ok:
                self.stdout.write(self.style.SUCCESS(f"  {field:20} : {value} ✓"))
            else:
                self.stdout.write(self.style.WARNING(f"  {field:20} : {value} ✗"))
                issues_found.append(field)
        
        # Check can_login() method
        can_login = user.can_login()
        if can_login:
            self.stdout.write(self.style.SUCCESS(f"  {'Can Login':20} : {can_login} ✓"))
        else:
            self.stdout.write(self.style.WARNING(f"  {'Can Login':20} : {can_login} ✗"))
            if 'Can Login' not in issues_found:
                issues_found.append('Can Login')
        
        # Display issues summary
        if issues_found:
            self.stdout.write(self.style.WARNING(f"\n⚠ Issues found: {', '.join(issues_found)}"))
            
            if options['fix']:
                self.stdout.write("\nApplying fixes...")
                
                # Fix all authentication-related fields
                user.is_active = True
                user.is_staff = True
                user.is_email_verified = True
                user.status = 'active'
                
                user.save()
                
                self.stdout.write(self.style.SUCCESS("✓ Fixed: is_active=True, is_staff=True, is_email_verified=True, status='active'"))
                
                # Re-check can_login
                if user.can_login():
                    self.stdout.write(self.style.SUCCESS("✓ User can now login"))
                else:
                    self.stdout.write(self.style.ERROR("✗ User still cannot login - check password or other issues"))
            else:
                self.stdout.write("\nTo fix these issues, run with --fix flag:")
                self.stdout.write(self.style.WARNING(f"  python manage.py fix_admin_user {email} --fix"))
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ No authentication issues found"))
        
        # Set new password if requested
        if options['set_password']:
            new_password = options['set_password']
            user.set_password(new_password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"\n✓ Password updated successfully"))
        
        # Test login if requested
        if options['test_login']:
            test_password = options['test_login']
            self.stdout.write(f"\nTesting login with provided password...")
            
            # Test with email parameter
            auth_user = authenticate(email=email, password=test_password)
            if auth_user:
                self.stdout.write(self.style.SUCCESS("✓ Login successful with email parameter"))
            else:
                self.stdout.write(self.style.WARNING("✗ Login failed with email parameter"))
            
            # Test with username parameter (for Django admin compatibility)
            auth_user = authenticate(username=email, password=test_password)
            if auth_user:
                self.stdout.write(self.style.SUCCESS("✓ Login successful with username parameter (Django admin compatible)"))
            else:
                self.stdout.write(self.style.WARNING("✗ Login failed with username parameter"))
                
            if not authenticate(email=email, password=test_password) and not authenticate(username=email, password=test_password):
                self.stdout.write(self.style.ERROR("\n✗ Authentication failed. Possible reasons:"))
                self.stdout.write("  1. Incorrect password")
                self.stdout.write("  2. Email not verified (is_email_verified=False)")
                self.stdout.write("  3. Account not active (is_active=False or status != 'active')")
                self.stdout.write("  4. Authentication backend issue")
        
        # Provide helpful next steps
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("Next Steps:")
        
        if not user.has_usable_password():
            self.stdout.write(self.style.WARNING("1. Set a password:"))
            self.stdout.write(f"   python manage.py fix_admin_user {email} --set-password YOUR_PASSWORD")
        
        if issues_found and not options['fix']:
            self.stdout.write(self.style.WARNING("2. Fix authentication issues:"))
            self.stdout.write(f"   python manage.py fix_admin_user {email} --fix")
        
        if not user.is_superuser and user.is_staff:
            self.stdout.write(self.style.WARNING("3. Make superuser (optional):"))
            self.stdout.write(f"   python manage.py shell -c \"from django.contrib.auth import get_user_model; User = get_user_model(); u = User.objects.get(email='{email}'); u.is_superuser = True; u.save()\"")
        
        self.stdout.write("\n4. Test login:")
        self.stdout.write(f"   python manage.py fix_admin_user {email} --test-login YOUR_PASSWORD")
        
        self.stdout.write("\n5. Try logging into Django admin:")
        self.stdout.write(f"   http://localhost:8000/admin/")
        self.stdout.write(f"   Email: {email}")
        self.stdout.write(f"   Password: YOUR_PASSWORD")
