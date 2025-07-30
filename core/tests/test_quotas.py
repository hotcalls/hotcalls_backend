"""
Tests for the quota enforcement system.
"""
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from unittest.mock import Mock, patch

from core.models import (
    Workspace, Plan, Feature, PlanFeature, EndpointFeature, 
    WorkspaceSubscription, WorkspaceUsage, FeatureUsage
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
        unlimited_feature = Feature.objects.create(
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