"""
Tests for the quota enforcement system.
"""
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from unittest.mock import Mock, patch
from django.test import Client
from django.core.cache import cache

from core.models import (
    Workspace, Plan, Feature, PlanFeature, EndpointFeature, 
    WorkspaceSubscription, FeatureUsage
)
from core.quotas import (
    enforce_and_record, QuotaExceeded, get_usage_container,
    current_billing_window, get_feature_usage_status
)
from core.middleware import PlanQuotaMiddleware

User = get_user_model()


class QuotaSystemTestCase(TestCase):
    """Base test case with common setup for quota tests."""
    
    def setUp(self):
        # Create user and workspace
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            phone='+1234567890',
            is_email_verified=True
        )
        
        self.workspace = Workspace.objects.create(
            workspace_name='Test Workspace'
        )
        self.workspace.users.add(self.user)
        
        # Create plan and feature
        self.plan = Plan.objects.create(
            plan_name='Test Plan',
            price_monthly=Decimal('10.00')
        )
        
        self.feature = Feature.objects.create(
            feature_name='API_CALLS',
            description='API call quota',
            unit='general_unit'
        )
        
        # Set plan limit
        self.plan_feature = PlanFeature.objects.create(
            plan=self.plan,
            feature=self.feature,
            limit=Decimal('100')  # 100 API calls allowed
        )
        
        # Create active subscription
        self.subscription = WorkspaceSubscription.objects.create(
            workspace=self.workspace,
            plan=self.plan,
            started_at=timezone.now(),
            is_active=True
        )
        
        # Create endpoint mapping
        self.endpoint = EndpointFeature.objects.create(
            feature=self.feature,
            route_name='test:api-endpoint',
            http_method='POST'
        )


class QuotaEnforcementTests(QuotaSystemTestCase):
    """Test quota enforcement logic."""
    
    def test_enforce_and_record_within_quota(self):
        """Test that requests within quota limits are allowed."""
        # Should succeed - within quota
        enforce_and_record(
            workspace=self.workspace,
            route_name='test:api-endpoint',
            http_method='POST',
            amount=50
        )
        
        # Check usage recorded
        usage_container = get_usage_container(self.workspace)
        feature_usage = FeatureUsage.objects.get(
            usage_record=usage_container,
            feature=self.feature
        )
        self.assertEqual(feature_usage.used_amount, Decimal('50'))
    
    def test_enforce_and_record_quota_exceeded(self):
        """Test that requests exceeding quota are blocked."""
        # First request that uses up quota
        enforce_and_record(
            workspace=self.workspace,
            route_name='test:api-endpoint',
            http_method='POST',
            amount=100
        )
        
        # Second request should exceed quota
        with self.assertRaises(QuotaExceeded) as context:
            enforce_and_record(
                workspace=self.workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=1
            )
        
        self.assertIn('API_CALLS', str(context.exception))
        self.assertIn('exceeds plan limit', str(context.exception))
    
    def test_enforce_and_record_unmetered_route(self):
        """Test that unmetered routes are not quota-enforced."""
        # Should succeed - route not in EndpointFeature
        enforce_and_record(
            workspace=self.workspace,
            route_name='unmetered:route',
            http_method='GET',
            amount=1000  # Large amount that would exceed quota
        )
        
        # No usage should be recorded
        usage_container = get_usage_container(self.workspace)
        feature_usage = FeatureUsage.objects.filter(
            usage_record=usage_container,
            feature=self.feature
        )
        self.assertFalse(feature_usage.exists())
    
    def test_get_feature_usage_status(self):
        """Test feature usage status reporting."""
        # Record some usage
        enforce_and_record(
            workspace=self.workspace,
            route_name='test:api-endpoint',
            http_method='POST',
            amount=30
        )
        
        status = get_feature_usage_status(self.workspace, 'API_CALLS')
        
        self.assertEqual(status['used'], Decimal('30'))
        self.assertEqual(status['limit'], Decimal('100'))
        self.assertEqual(status['remaining'], Decimal('70'))
        self.assertFalse(status['unlimited'])
    
    def test_unlimited_feature(self):
        """Test behavior with unlimited features."""
        # Create feature without plan limit
        Feature.objects.create(
            feature_name='UNLIMITED_FEATURE',
            description='Unlimited feature'
        )
        
        # No PlanFeature entry = unlimited
        status = get_feature_usage_status(self.workspace, 'UNLIMITED_FEATURE')
        
        self.assertTrue(status['unlimited'])
        self.assertIsNone(status['limit'])
        self.assertIsNone(status['remaining'])


class MiddlewareTests(QuotaSystemTestCase):
    """Test quota middleware functionality."""
    
    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.middleware = PlanQuotaMiddleware(Mock())
        
        # Mock resolver match
        self.mock_resolver_match = Mock()
        self.mock_resolver_match.view_name = 'test:api-endpoint'
        
    def test_middleware_allows_within_quota(self):
        """Test middleware allows requests within quota."""
        request = self.factory.post('/api/test/')
        request.user = self.user
        request.resolver_match = self.mock_resolver_match
        
        # Mock workspace access
        with patch.object(self.middleware, '_get_workspace', return_value=self.workspace):
            response = self.middleware.process_view(request, Mock(), [], {})
        
        # Should return None (allow request)
        self.assertIsNone(response)
    
    def test_middleware_blocks_quota_exceeded(self):
        """Test middleware blocks requests when quota exceeded."""
        # Use up quota first
        enforce_and_record(
            workspace=self.workspace,
            route_name='test:api-endpoint',
            http_method='POST',
            amount=100
        )
        
        request = self.factory.post('/api/test/')
        request.user = self.user
        request.resolver_match = self.mock_resolver_match
        
        # Mock workspace access
        with patch.object(self.middleware, '_get_workspace', return_value=self.workspace):
            response = self.middleware.process_view(request, Mock(), [], {})
        
        # Should return 403 response
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        
    def test_middleware_ignores_unauthenticated(self):
        """Test middleware ignores unauthenticated requests."""
        request = self.factory.post('/api/test/')
        request.user = Mock()
        request.user.is_authenticated = False
        
        response = self.middleware.process_view(request, Mock(), [], {})
        
        # Should return None (allow request)
        self.assertIsNone(response)
    
    def test_middleware_ignores_unmetered_routes(self):
        """Test middleware ignores routes not in EndpointFeature."""
        request = self.factory.get('/api/unmetered/')
        request.user = self.user
        
        # Mock unmetered route
        mock_resolver_match = Mock()
        mock_resolver_match.view_name = 'unmetered:route'
        request.resolver_match = mock_resolver_match
        
        with patch.object(self.middleware, '_get_workspace', return_value=self.workspace):
            response = self.middleware.process_view(request, Mock(), [], {})
        
        # Should return None (allow request)
        self.assertIsNone(response)


class BillingWindowTests(QuotaSystemTestCase):
    """Test billing window calculations."""
    
    def test_current_billing_window(self):
        """Test billing window calculation."""
        # Set subscription start to a known date
        start_date = timezone.datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        self.subscription.started_at = start_date
        self.subscription.save()
        
        with patch('django.utils.timezone.now') as mock_now:
            # Mock current time to be in the same billing period
            mock_now.return_value = timezone.datetime(2024, 1, 20, 15, 0, 0, tzinfo=timezone.utc)
            
            period_start, period_end = current_billing_window(self.subscription)
            
            # Should be same month
            self.assertEqual(period_start.day, 15)
            self.assertEqual(period_start.month, 1)
            self.assertEqual(period_end.day, 15)
            self.assertEqual(period_end.month, 2)
            
    def test_billing_window_month_overflow(self):
        """Test billing window handles month overflow correctly."""
        # Start on Jan 31
        start_date = timezone.datetime(2024, 1, 31, 10, 0, 0, tzinfo=timezone.utc)
        self.subscription.started_at = start_date
        self.subscription.save()
        
        with patch('django.utils.timezone.now') as mock_now:
            # Mock current time to be in February
            mock_now.return_value = timezone.datetime(2024, 2, 15, 15, 0, 0, tzinfo=timezone.utc)
            
            period_start, period_end = current_billing_window(self.subscription)
            
            # Feb 31 doesn't exist, should use Feb 28/29
            self.assertEqual(period_start.month, 1)
            self.assertEqual(period_start.day, 31)
            # End should be Feb 28 (2024 is leap year, so Feb 29)
            self.assertEqual(period_end.month, 2)
            self.assertEqual(period_end.day, 29)  # 2024 is a leap year


class MultiWorkspaceTests(TestCase):
    """Test quota enforcement with multiple workspaces."""
    
    def setUp(self):
        # Create user
        self.user = User.objects.create_user(
            email='multiuser@example.com',
            password='testpass123',
            first_name='Multi',
            last_name='User',
            phone='+1234567890',
            is_email_verified=True
        )
        
        # Create multiple workspaces
        self.workspace1 = Workspace.objects.create(workspace_name='Workspace 1')
        self.workspace2 = Workspace.objects.create(workspace_name='Workspace 2')
        
        # Add user to both workspaces
        self.workspace1.users.add(self.user)
        self.workspace2.users.add(self.user)
        
        # Create different plans
        self.basic_plan = Plan.objects.create(
            plan_name='Basic Plan',
            price_monthly=Decimal('5.00')
        )
        self.premium_plan = Plan.objects.create(
            plan_name='Premium Plan', 
            price_monthly=Decimal('20.00')
        )
        
        # Create feature
        self.feature = Feature.objects.create(
            feature_name='API_CALLS',
            description='API call quota',
            unit='general_unit'
        )
        
        # Set different limits for each plan
        PlanFeature.objects.create(
            plan=self.basic_plan,
            feature=self.feature,
            limit=Decimal('50')  # Basic: 50 calls
        )
        PlanFeature.objects.create(
            plan=self.premium_plan,
            feature=self.feature,
            limit=Decimal('500')  # Premium: 500 calls
        )
        
        # Create subscriptions for different workspaces
        self.subscription1 = WorkspaceSubscription.objects.create(
            workspace=self.workspace1,
            plan=self.basic_plan,
            started_at=timezone.now(),
            is_active=True
        )
        self.subscription2 = WorkspaceSubscription.objects.create(
            workspace=self.workspace2,
            plan=self.premium_plan,
            started_at=timezone.now(),
            is_active=True
        )
        
        # Create endpoint mapping
        self.endpoint = EndpointFeature.objects.create(
            feature=self.feature,
            route_name='test:api-endpoint',
            http_method='POST'
        )
    
    def test_cross_workspace_quota_isolation(self):
        """Test that quota usage is isolated between workspaces."""
        # Use up quota in workspace1 (Basic plan: 50 limit)
        enforce_and_record(
            workspace=self.workspace1,
            route_name='test:api-endpoint',
            http_method='POST',
            amount=50
        )
        
        # Workspace1 should be at limit
        with self.assertRaises(QuotaExceeded):
            enforce_and_record(
                workspace=self.workspace1,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=1
            )
        
        # Workspace2 should still have full quota available
        enforce_and_record(
            workspace=self.workspace2,
            route_name='test:api-endpoint',
            http_method='POST',
            amount=100  # Should succeed - Premium plan has 500 limit
        )
        
        # Verify usage is tracked separately
        status1 = get_feature_usage_status(self.workspace1, 'API_CALLS')
        status2 = get_feature_usage_status(self.workspace2, 'API_CALLS')
        
        self.assertEqual(status1['used'], Decimal('50'))
        self.assertEqual(status1['limit'], Decimal('50'))
        self.assertEqual(status2['used'], Decimal('100'))
        self.assertEqual(status2['limit'], Decimal('500'))
    
    def test_different_plans_per_workspace(self):
        """Test that different workspaces can have different plan limits."""
        # Test workspace1 with Basic plan (50 limit)
        for i in range(50):
            enforce_and_record(
                workspace=self.workspace1,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=1
            )
        
        # 51st call should fail for workspace1
        with self.assertRaises(QuotaExceeded):
            enforce_and_record(
                workspace=self.workspace1,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=1
            )
        
        # But workspace2 with Premium plan should handle much more
        for i in range(450):  # 450 more calls (total 500)
            enforce_and_record(
                workspace=self.workspace2,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=1
            )
        
        # Verify workspace2 is at limit but workspace1 hasn't changed
        status1 = get_feature_usage_status(self.workspace1, 'API_CALLS')
        status2 = get_feature_usage_status(self.workspace2, 'API_CALLS')
        
        self.assertEqual(status1['used'], Decimal('50'))
        self.assertEqual(status2['used'], Decimal('450'))
    
    def test_workspace_switching_behavior(self):
        """Test quota tracking when user operates across workspaces."""
        # Simulate rapid workspace switching
        for i in range(10):
            # Alternate between workspaces
            workspace = self.workspace1 if i % 2 == 0 else self.workspace2
            
            enforce_and_record(
                workspace=workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=1
            )
        
        # Verify usage is correctly attributed
        status1 = get_feature_usage_status(self.workspace1, 'API_CALLS')
        status2 = get_feature_usage_status(self.workspace2, 'API_CALLS')
        
        # 5 calls each (0,2,4,6,8 vs 1,3,5,7,9)
        self.assertEqual(status1['used'], Decimal('5'))
        self.assertEqual(status2['used'], Decimal('5'))


class BillingPeriodBoundaryTests(TestCase):
    """Test time-sensitive billing period scenarios."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='billing@example.com',
            password='testpass123',
            first_name='Billing',
            last_name='User',
            phone='+1234567890',
            is_email_verified=True
        )
        
        self.workspace = Workspace.objects.create(workspace_name='Billing Workspace')
        self.workspace.users.add(self.user)
        
        self.plan = Plan.objects.create(
            plan_name='Billing Plan',
            price_monthly=Decimal('10.00')
        )
        
        self.feature = Feature.objects.create(
            feature_name='API_CALLS',
            description='API call quota',
            unit='general_unit'
        )
        
        PlanFeature.objects.create(
            plan=self.plan,
            feature=self.feature,
            limit=Decimal('100')
        )
        
        EndpointFeature.objects.create(
            feature=self.feature,
            route_name='test:api-endpoint',
            http_method='POST'
        )
    
    def test_usage_near_billing_period_end(self):
        """Test behavior when usage occurs near billing period boundary."""
        # Set subscription start to create predictable billing period
        start_date = timezone.datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        WorkspaceSubscription.objects.create(
            workspace=self.workspace,
            plan=self.plan,
            started_at=start_date,
            is_active=True
        )
        
        # Mock time near end of billing period (Feb 14, 23:59)
        near_end_time = timezone.datetime(2024, 2, 14, 23, 59, 0, tzinfo=timezone.utc)
        
        with patch('django.utils.timezone.now', return_value=near_end_time):
            # Use up most of quota
            enforce_and_record(
                workspace=self.workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=99
            )
            
            # Should have 1 call remaining
            status = get_feature_usage_status(self.workspace, 'API_CALLS')
            self.assertEqual(status['remaining'], Decimal('1'))
    
    def test_quota_reset_at_period_start(self):
        """Test that quota resets at the start of new billing period."""
        start_date = timezone.datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        WorkspaceSubscription.objects.create(
            workspace=self.workspace,
            plan=self.plan,
            started_at=start_date,
            is_active=True
        )
        
        # Use quota in first period
        first_period_time = timezone.datetime(2024, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
        with patch('django.utils.timezone.now', return_value=first_period_time):
            enforce_and_record(
                workspace=self.workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=100  # Use full quota
            )
            
            # Should be at limit
            with self.assertRaises(QuotaExceeded):
                enforce_and_record(
                    workspace=self.workspace,
                    route_name='test:api-endpoint',
                    http_method='POST',
                    amount=1
                )
        
        # Move to next billing period
        next_period_time = timezone.datetime(2024, 2, 16, 12, 0, 0, tzinfo=timezone.utc)
        with patch('django.utils.timezone.now', return_value=next_period_time):
            # Should have fresh quota
            enforce_and_record(
                workspace=self.workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=50  # Should succeed with new quota
            )
            
            status = get_feature_usage_status(self.workspace, 'API_CALLS')
            self.assertEqual(status['used'], Decimal('50'))
            self.assertEqual(status['remaining'], Decimal('50'))
    
    def test_leap_year_billing_periods(self):
        """Test billing period calculation during leap years."""
        # Start subscription on Feb 29, 2024 (leap year)
        leap_start = timezone.datetime(2024, 2, 29, 10, 0, 0, tzinfo=timezone.utc)
        subscription = WorkspaceSubscription.objects.create(
            workspace=self.workspace,
            plan=self.plan,
            started_at=leap_start,
            is_active=True
        )
        
        # Test in March 2024 (should handle Feb 29 -> Mar 29)
        march_time = timezone.datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        with patch('django.utils.timezone.now', return_value=march_time):
            period_start, period_end = current_billing_window(subscription)
            
            # Should be Feb 29 -> Mar 29
            self.assertEqual(period_start.month, 2)
            self.assertEqual(period_start.day, 29)
            self.assertEqual(period_end.month, 3) 
            self.assertEqual(period_end.day, 29)
        
        # Test in 2025 (non-leap year) - should handle Feb 29 -> Feb 28
        feb_2025_time = timezone.datetime(2025, 2, 15, 12, 0, 0, tzinfo=timezone.utc)
        with patch('django.utils.timezone.now', return_value=feb_2025_time):
            period_start, period_end = current_billing_window(subscription)
            
            # Should be Jan 29 -> Feb 28 (no Feb 29 in 2025)
            self.assertEqual(period_start.month, 1)
            self.assertEqual(period_start.day, 29)
            self.assertEqual(period_end.month, 2)
            self.assertEqual(period_end.day, 28)  # Non-leap year
    
    def test_subscription_renewal_timing(self):
        """Test quota behavior during subscription renewal."""
        start_date = timezone.datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        WorkspaceSubscription.objects.create(
            workspace=self.workspace,
            plan=self.plan,
            started_at=start_date,
            is_active=True
        )
        
        # Use quota before renewal
        before_renewal = timezone.datetime(2024, 2, 14, 12, 0, 0, tzinfo=timezone.utc)
        with patch('django.utils.timezone.now', return_value=before_renewal):
            enforce_and_record(
                workspace=self.workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=75
            )
        
        # At renewal time, quota should reset
        renewal_time = timezone.datetime(2024, 2, 15, 10, 0, 0, tzinfo=timezone.utc)
        with patch('django.utils.timezone.now', return_value=renewal_time):
            # Should be able to use full quota again
            enforce_and_record(
                workspace=self.workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=100
            )
            
            status = get_feature_usage_status(self.workspace, 'API_CALLS')
            self.assertEqual(status['used'], Decimal('100'))
            self.assertEqual(status['remaining'], Decimal('0'))


class DataIntegrityEdgeCaseTests(TestCase):
    """Test data integrity and unusual scenarios."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='edge@example.com',
            password='testpass123',
            first_name='Edge',
            last_name='User',
            phone='+1234567890',
            is_email_verified=True
        )
        
        self.workspace = Workspace.objects.create(workspace_name='Edge Workspace')
        self.workspace.users.add(self.user)
        
        self.plan = Plan.objects.create(
            plan_name='Edge Plan',
            price_monthly=Decimal('10.00')
        )
        
        self.feature = Feature.objects.create(
            feature_name='API_CALLS',
            description='API call quota',
            unit='general_unit'
        )
        
        PlanFeature.objects.create(
            plan=self.plan,
            feature=self.feature,
            limit=Decimal('1000.000')  # High precision limit
        )
        
        WorkspaceSubscription.objects.create(
            workspace=self.workspace,
            plan=self.plan,
            started_at=timezone.now(),
            is_active=True
        )
        
        EndpointFeature.objects.create(
            feature=self.feature,
            route_name='test:api-endpoint',
            http_method='POST'
        )
    
    def test_negative_usage_amounts(self):
        """Test that negative usage amounts are rejected."""
        with self.assertRaises(Exception):  # Should fail validation
            enforce_and_record(
                workspace=self.workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=-10  # Negative amount
            )
    
    def test_zero_usage_amount(self):
        """Test zero usage amount handling."""
        # Zero amount should succeed but not change usage
        enforce_and_record(
            workspace=self.workspace,
            route_name='test:api-endpoint',
            http_method='POST',
            amount=0
        )
        
        status = get_feature_usage_status(self.workspace, 'API_CALLS')
        self.assertEqual(status['used'], Decimal('0'))
    
    def test_extremely_large_quota_limits(self):
        """Test handling of very large quota limits."""
        # Create feature with maximum decimal value
        large_feature = Feature.objects.create(
            feature_name='LARGE_QUOTA',
            description='Large quota test',
            unit='general_unit'
        )
        
        max_limit = Decimal('999999999999.999')  # Max digits/decimal places
        PlanFeature.objects.create(
            plan=self.plan,
            feature=large_feature,
            limit=max_limit
        )
        
        EndpointFeature.objects.create(
            feature=large_feature,
            route_name='test:large-endpoint',
            http_method='POST'
        )
        
        # Should handle large usage amounts
        large_amount = Decimal('1000000.000')
        enforce_and_record(
            workspace=self.workspace,
            route_name='test:large-endpoint',
            http_method='POST',
            amount=large_amount
        )
        
        status = get_feature_usage_status(self.workspace, 'LARGE_QUOTA')
        self.assertEqual(status['used'], large_amount)
        self.assertEqual(status['limit'], max_limit)
    
    def test_decimal_precision_edge_cases(self):
        """Test decimal precision handling."""
        # Test very precise decimal values
        precise_amounts = [
            Decimal('0.001'),
            Decimal('0.0001'),
            Decimal('1.999'),
            Decimal('99.999')
        ]
        
        total_used = Decimal('0')
        for amount in precise_amounts:
            enforce_and_record(
                workspace=self.workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=amount
            )
            total_used += amount
        
        status = get_feature_usage_status(self.workspace, 'API_CALLS')
        self.assertEqual(status['used'], total_used)
        
        # Verify precision is maintained
        expected_total = Decimal('102.0001')
        self.assertEqual(status['used'], expected_total)
    
    def test_feature_unit_consistency(self):
        """Test that feature units are handled consistently."""
        # Create features with different units
        minute_feature = Feature.objects.create(
            feature_name='MINUTES',
            description='Time-based feature',
            unit='minute'
        )
        
        request_feature = Feature.objects.create(
            feature_name='REQUESTS',
            description='Request-based feature', 
            unit='request'
        )
        
        gb_feature = Feature.objects.create(
            feature_name='STORAGE',
            description='Storage feature',
            unit='gb'
        )
        
        # Add to plan with appropriate limits
        PlanFeature.objects.create(plan=self.plan, feature=minute_feature, limit=Decimal('120.0'))  # 2 hours
        PlanFeature.objects.create(plan=self.plan, feature=request_feature, limit=Decimal('10000'))  # 10k requests
        PlanFeature.objects.create(plan=self.plan, feature=gb_feature, limit=Decimal('5.0'))  # 5 GB
        
        # Create endpoints for each
        EndpointFeature.objects.create(feature=minute_feature, route_name='test:minutes', http_method='POST')
        EndpointFeature.objects.create(feature=request_feature, route_name='test:requests', http_method='POST') 
        EndpointFeature.objects.create(feature=gb_feature, route_name='test:storage', http_method='POST')
        
        # Test each unit type
        enforce_and_record(workspace=self.workspace, route_name='test:minutes', amount=Decimal('30.5'))  # 30.5 minutes
        enforce_and_record(workspace=self.workspace, route_name='test:requests', amount=1000)  # 1000 requests
        enforce_and_record(workspace=self.workspace, route_name='test:storage', amount=Decimal('0.5'))  # 0.5 GB
        
        # Verify usage tracking
        minute_status = get_feature_usage_status(self.workspace, 'MINUTES')
        request_status = get_feature_usage_status(self.workspace, 'REQUESTS')
        storage_status = get_feature_usage_status(self.workspace, 'STORAGE')
        
        self.assertEqual(minute_status['used'], Decimal('30.5'))
        self.assertEqual(request_status['used'], Decimal('1000'))
        self.assertEqual(storage_status['used'], Decimal('0.5'))
    
    def test_float_to_decimal_conversion(self):
        """Test proper handling of float to decimal conversion."""
        # Test common float precision issues
        float_amounts = [0.1, 0.2, 0.3]  # These can cause precision issues in float
        
        for amount in float_amounts:
            enforce_and_record(
                workspace=self.workspace,
                route_name='test:api-endpoint',
                http_method='POST',
                amount=amount  # Function should convert to Decimal
            )
        
        status = get_feature_usage_status(self.workspace, 'API_CALLS')
        # Should equal 0.6 exactly (no floating point errors)
        self.assertEqual(status['used'], Decimal('0.6'))


class IntegrationTests(TestCase):
    """Integration tests for real HTTP request flows."""
    
    def setUp(self):
        # Create test user and workspace
        self.user = User.objects.create_user(
            email='integration@example.com',
            password='testpass123',
            first_name='Integration',
            last_name='User',
            phone='+1234567890',
            is_email_verified=True
        )
        
        self.workspace = Workspace.objects.create(workspace_name='Integration Workspace')
        self.workspace.users.add(self.user)
        
        # Create plan and feature
        self.plan = Plan.objects.create(
            plan_name='Integration Plan',
            price_monthly=Decimal('15.00')
        )
        
        self.feature = Feature.objects.create(
            feature_name='API_CALLS',
            description='API call quota',
            unit='general_unit'
        )
        
        PlanFeature.objects.create(
            plan=self.plan,
            feature=self.feature,
            limit=Decimal('10')  # Low limit for testing
        )
        
        WorkspaceSubscription.objects.create(
            workspace=self.workspace,
            plan=self.plan,
            started_at=timezone.now(),
            is_active=True
        )
        
        # Create test client
        self.client = Client()
        
        # Clear cache before each test
        cache.clear()
    
    def test_http_request_quota_enforcement_flow(self):
        """Test full HTTP request flow with quota enforcement."""
        # Create endpoint that will be quota-enforced
        EndpointFeature.objects.create(
            feature=self.feature,
            route_name='test_integration_view',
            http_method='POST'
        )
        
        # Mock a user having workspace access
        with patch('core.middleware.PlanQuotaMiddleware._get_workspace', return_value=self.workspace):
            # Create factory request with proper setup
            factory = RequestFactory()
            middleware = PlanQuotaMiddleware(Mock())
            
            # Mock resolver match
            mock_resolver_match = Mock()
            mock_resolver_match.view_name = 'test_integration_view'
            
            # Test requests within quota (should all succeed)
            for i in range(10):
                request = factory.post('/api/test/')
                request.user = self.user
                request.resolver_match = mock_resolver_match
                
                response = middleware.process_view(request, Mock(), [], {})
                self.assertIsNone(response)  # Should allow request
            
            # 11th request should be blocked
            request = factory.post('/api/test/')
            request.user = self.user
            request.resolver_match = mock_resolver_match
            
            response = middleware.process_view(request, Mock(), [], {})
            self.assertIsNotNone(response)
            self.assertEqual(response.status_code, 403)
            
            # Verify quota status
            status = get_feature_usage_status(self.workspace, 'API_CALLS')
            self.assertEqual(status['used'], Decimal('10'))
            self.assertEqual(status['remaining'], Decimal('0'))
    
    def test_cache_performance_under_load(self):
        """Test cache hit/miss behavior under repeated requests."""
        EndpointFeature.objects.create(
            feature=self.feature,
            route_name='test_cache_view',
            http_method='GET'
        )
        
        factory = RequestFactory()
        middleware = PlanQuotaMiddleware(Mock())
        
        # First request should miss cache and populate it
        request = factory.get('/api/cache-test/')
        request.user = self.user
        
        mock_resolver_match = Mock()
        mock_resolver_match.view_name = 'test_cache_view'
        request.resolver_match = mock_resolver_match
        
        with patch('core.middleware.PlanQuotaMiddleware._get_workspace', return_value=self.workspace):
            # Monitor cache operations
            original_get = cache.get
            original_set = cache.set
            
            cache_gets = []
            cache_sets = []
            
            def mock_cache_get(key, default=None):
                cache_gets.append(key)
                return original_get(key, default)
            
            def mock_cache_set(key, value, timeout=None):
                cache_sets.append(key)
                return original_set(key, value, timeout)
            
            with patch.object(cache, 'get', side_effect=mock_cache_get):
                with patch.object(cache, 'set', side_effect=mock_cache_set):
                    # First request - should cache miss and set
                    middleware.process_view(request, Mock(), [], {})
                    
                    # Subsequent requests - should hit cache
                    for _ in range(5):
                        middleware.process_view(request, Mock(), [], {})
            
            # Verify cache behavior
            self.assertEqual(len(cache_sets), 1)  # Should only set cache once
            self.assertEqual(len(cache_gets), 6)  # Should get from cache 6 times
    
    def test_concurrent_request_handling(self):
        """Test quota enforcement under concurrent requests."""
        EndpointFeature.objects.create(
            feature=self.feature,
            route_name='test_concurrent_view',
            http_method='POST'
        )
        
        # Test atomic operations by simulating concurrent requests
        from threading import Thread
        import threading
        
        results = []
        lock = threading.Lock()
        
        def make_request(request_id):
            try:
                enforce_and_record(
                    workspace=self.workspace,
                    route_name='test_concurrent_view',
                    http_method='POST',
                    amount=1
                )
                with lock:
                    results.append(f'success_{request_id}')
            except QuotaExceeded:
                with lock:
                    results.append(f'quota_exceeded_{request_id}')
        
        # Launch 15 concurrent "requests" (more than the 10 limit)
        threads = []
        for i in range(15):
            thread = Thread(target=make_request, args=(i,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all to complete
        for thread in threads:
            thread.join()
        
        # Count results
        successes = [r for r in results if r.startswith('success')]
        quota_exceeded = [r for r in results if r.startswith('quota_exceeded')]
        
        # Should have exactly 10 successes and 5 quota exceeded
        self.assertEqual(len(successes), 10)
        self.assertEqual(len(quota_exceeded), 5)
        
        # Verify final quota state
        status = get_feature_usage_status(self.workspace, 'API_CALLS')
        self.assertEqual(status['used'], Decimal('10'))
    
    def test_cache_invalidation_on_endpoint_changes(self):
        """Test that cache is properly invalidated when EndpointFeature changes."""
        # Create initial endpoint
        endpoint = EndpointFeature.objects.create(
            feature=self.feature,
            route_name='test_invalidation_view',
            http_method='POST'
        )
        
        factory = RequestFactory()
        middleware = PlanQuotaMiddleware(Mock())
        
        # Make a request to populate cache
        request = factory.post('/api/invalidation-test/')
        request.user = self.user
        
        mock_resolver_match = Mock()
        mock_resolver_match.view_name = 'test_invalidation_view'
        request.resolver_match = mock_resolver_match
        
        with patch('core.middleware.PlanQuotaMiddleware._get_workspace', return_value=self.workspace):
            # First request populates cache
            response = middleware.process_view(request, Mock(), [], {})
            self.assertIsNone(response)  # Should succeed (quota enforced)
            
            # Verify cache key exists
            cache_key = "endpoint_feature:POST:test_invalidation_view"
            cached_value = cache.get(cache_key)
            self.assertIsNotNone(cached_value)
            
            # Delete the endpoint (should trigger cache invalidation)
            endpoint.delete()
            
            # Cache should be invalidated
            cached_value_after_delete = cache.get(cache_key)
            self.assertIsNone(cached_value_after_delete)
            
            # Subsequent request should not enforce quota (no endpoint mapping)
            response = middleware.process_view(request, Mock(), [], {})
            self.assertIsNone(response)  # Should succeed (no quota enforcement)


class VirtualRouteFrameworkTests(TestCase):
    """Test virtual route framework functionality."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='virtual@example.com',
            password='testpass123',
            first_name='Virtual',
            last_name='User',
            phone='+1234567890',
            is_email_verified=True
        )
        
        self.workspace = Workspace.objects.create(workspace_name='Virtual Workspace')
        self.workspace.users.add(self.user)
        
        self.plan = Plan.objects.create(
            plan_name='Virtual Plan',
            price_monthly=Decimal('20.00')
        )
        
        # Create different types of features for virtual routes
        self.api_feature = Feature.objects.create(
            feature_name='VIRTUAL_API_CALLS',
            description='Virtual API operations',
            unit='general_unit'
        )
        
        self.processing_feature = Feature.objects.create(
            feature_name='BACKGROUND_PROCESSING',
            description='Background job processing',
            unit='minute'
        )
        
        self.webhook_feature = Feature.objects.create(
            feature_name='WEBHOOK_EVENTS',
            description='Webhook event processing',
            unit='request'
        )
        
        # Set limits
        PlanFeature.objects.create(plan=self.plan, feature=self.api_feature, limit=Decimal('100'))
        PlanFeature.objects.create(plan=self.plan, feature=self.processing_feature, limit=Decimal('60'))  # 1 hour
        PlanFeature.objects.create(plan=self.plan, feature=self.webhook_feature, limit=Decimal('1000'))
        
        WorkspaceSubscription.objects.create(
            workspace=self.workspace,
            plan=self.plan,
            started_at=timezone.now(),
            is_active=True
        )
    
    def test_internal_virtual_routes(self):
        """Test internal: namespace virtual routes."""
        # Create virtual endpoints
        EndpointFeature.objects.create(
            feature=self.api_feature,
            route_name='internal:ai_analysis',
            http_method='POST'
        )
        
        EndpointFeature.objects.create(
            feature=self.processing_feature,
            route_name='internal:data_processing',
            http_method='POST'
        )
        
        # Test internal AI analysis virtual route
        for i in range(50):
            enforce_and_record(
                workspace=self.workspace,
                route_name='internal:ai_analysis',
                http_method='POST',
                amount=1
            )
        
        # Test internal data processing (time-based)
        enforce_and_record(
            workspace=self.workspace,
            route_name='internal:data_processing',
            http_method='POST',
            amount=Decimal('30.5')  # 30.5 minutes
        )
        
        # Verify usage tracking
        api_status = get_feature_usage_status(self.workspace, 'VIRTUAL_API_CALLS')
        processing_status = get_feature_usage_status(self.workspace, 'BACKGROUND_PROCESSING')
        
        self.assertEqual(api_status['used'], Decimal('50'))
        self.assertEqual(api_status['remaining'], Decimal('50'))
        self.assertEqual(processing_status['used'], Decimal('30.5'))
        self.assertEqual(processing_status['remaining'], Decimal('29.5'))
    
    def test_webhook_virtual_routes(self):
        """Test webhook: namespace virtual routes."""
        EndpointFeature.objects.create(
            feature=self.webhook_feature,
            route_name='webhook:meta_leadgen',
            http_method='POST'
        )
        
        EndpointFeature.objects.create(
            feature=self.webhook_feature,
            route_name='webhook:stripe_payment',
            http_method='POST'
        )
        
        # Simulate webhook processing
        webhook_types = ['webhook:meta_leadgen', 'webhook:stripe_payment']
        
        for webhook_type in webhook_types:
            for i in range(100):  # 100 events per type
                enforce_and_record(
                    workspace=self.workspace,
                    route_name=webhook_type,
                    http_method='POST',
                    amount=1
                )
        
        # Should have used 200 webhook events total
        status = get_feature_usage_status(self.workspace, 'WEBHOOK_EVENTS')
        self.assertEqual(status['used'], Decimal('200'))
        self.assertEqual(status['remaining'], Decimal('800'))
    
    def test_worker_virtual_routes(self):
        """Test worker: namespace virtual routes."""
        EndpointFeature.objects.create(
            feature=self.processing_feature,
            route_name='worker:lead_import',
            http_method='POST'
        )
        
        # Simulate background worker processing
        job_durations = [Decimal('5.5'), Decimal('12.0'), Decimal('8.25'), Decimal('15.75')]  # minutes
        
        for duration in job_durations:
            enforce_and_record(
                workspace=self.workspace,
                route_name='worker:lead_import',
                http_method='POST',
                amount=duration
            )
        
        expected_total = sum(job_durations)  # 41.5 minutes
        status = get_feature_usage_status(self.workspace, 'BACKGROUND_PROCESSING')
        
        self.assertEqual(status['used'], expected_total)
        self.assertEqual(status['remaining'], Decimal('60') - expected_total)
    
    def test_virtual_route_quota_exceeded(self):
        """Test quota exceeded behavior for virtual routes."""
        EndpointFeature.objects.create(
            feature=self.api_feature,
            route_name='internal:heavy_operation',
            http_method='POST'
        )
        
        # Use up quota
        enforce_and_record(
            workspace=self.workspace,
            route_name='internal:heavy_operation',
            http_method='POST',
            amount=100  # Full quota
        )
        
        # Next operation should exceed quota
        with self.assertRaises(QuotaExceeded) as context:
            enforce_and_record(
                workspace=self.workspace,
                route_name='internal:heavy_operation',
                http_method='POST',
                amount=1
            )
        
        self.assertIn('VIRTUAL_API_CALLS', str(context.exception))
        self.assertIn('exceeds plan limit', str(context.exception))
    
    def test_unmetered_virtual_routes(self):
        """Test virtual routes that are not metered."""
        # Call virtual route that has no EndpointFeature mapping
        enforce_and_record(
            workspace=self.workspace,
            route_name='internal:unmetered_operation',
            http_method='POST',
            amount=9999  # Large amount that would exceed any quota
        )
        
        # Should succeed and not record any usage
        api_status = get_feature_usage_status(self.workspace, 'VIRTUAL_API_CALLS')
        self.assertEqual(api_status['used'], Decimal('0'))
    
    def test_mixed_real_and_virtual_routes(self):
        """Test that real HTTP routes and virtual routes share the same quota."""
        # Create both real and virtual endpoints for same feature
        EndpointFeature.objects.create(
            feature=self.api_feature,
            route_name='real:api-endpoint',  # "Real" HTTP route
            http_method='POST'
        )
        
        EndpointFeature.objects.create(
            feature=self.api_feature,
            route_name='internal:background_api',  # Virtual route
            http_method='POST'
        )
        
        # Use quota from "real" route
        enforce_and_record(
            workspace=self.workspace,
            route_name='real:api-endpoint',
            http_method='POST',
            amount=60
        )
        
        # Use quota from virtual route
        enforce_and_record(
            workspace=self.workspace,
            route_name='internal:background_api',
            http_method='POST',
            amount=30
        )
        
        # Should have used 90 total from same feature
        status = get_feature_usage_status(self.workspace, 'VIRTUAL_API_CALLS')
        self.assertEqual(status['used'], Decimal('90'))
        self.assertEqual(status['remaining'], Decimal('10'))
        
        # Next operation from either route should exceed if > 10
        with self.assertRaises(QuotaExceeded):
            enforce_and_record(
                workspace=self.workspace,
                route_name='internal:background_api',
                http_method='POST',
                amount=11  # Would exceed remaining 10
            )
    
    def test_virtual_route_naming_conventions(self):
        """Test various virtual route naming patterns."""
        virtual_routes = [
            'internal:call_dnd_bypass',
            'webhook:meta_integration', 
            'worker:ai_voice_synthesis',
            'cron:daily_cleanup',
            'ai:sentiment_analysis',
            'test:mock_operation'
        ]
        
        # Create endpoints for all patterns
        for route in virtual_routes:
            EndpointFeature.objects.create(
                feature=self.api_feature,
                route_name=route,
                http_method='POST'
            )
        
        # Test each pattern
        for i, route in enumerate(virtual_routes):
            enforce_and_record(
                workspace=self.workspace,
                route_name=route,
                http_method='POST',
                amount=5  # 5 * 6 = 30 total
            )
        
        status = get_feature_usage_status(self.workspace, 'VIRTUAL_API_CALLS')
        self.assertEqual(status['used'], Decimal('30'))  # 6 routes * 5 each
        self.assertEqual(status['remaining'], Decimal('70'))