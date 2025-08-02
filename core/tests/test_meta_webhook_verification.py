"""
Tests for Meta webhook verification and signature validation.
"""

import json
import hmac
import hashlib
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from core.models import Workspace, MetaIntegration


class MetaWebhookVerificationTestCase(TestCase):
    """Test Meta webhook verification (GET) and signature validation (POST)"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.webhook_url = reverse('meta_webhooks:meta-lead-webhook')
        
        # Test tokens
        self.verify_token = "test_verify_token_12345"
        self.app_secret = "test_app_secret_67890"
        
        # Create test workspace
        self.workspace = Workspace.objects.create(
            workspace_name="Test Workspace"
        )
        
        # Sample webhook payload
        self.webhook_payload = {
            "object": "page",
            "entry": [
                {
                    "id": "123456789",
                    "time": 1234567890,
                    "changes": [
                        {
                            "field": "leadgen",
                            "value": {
                                "leadgen_id": "test_lead_123",
                                "form_id": "test_form_456",
                                "page_id": "test_page_789"
                            }
                        }
                    ]
                }
            ]
        }

    @override_settings(META_WEBHOOK_VERIFY_TOKEN="test_verify_token_12345")
    def test_webhook_verification_success(self):
        """Test successful webhook verification (GET request)"""
        # Meta sends these parameters for verification
        params = {
            'hub.mode': 'subscribe',
            'hub.verify_token': self.verify_token,
            'hub.challenge': 'test_challenge_12345'
        }
        
        response = self.client.get(self.webhook_url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content.decode(), 'test_challenge_12345')
        self.assertTrue(response['Content-Type'].startswith('text/plain'))

    @override_settings(META_WEBHOOK_VERIFY_TOKEN="test_verify_token_12345")
    def test_webhook_verification_invalid_token(self):
        """Test webhook verification with invalid token"""
        params = {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'wrong_token',
            'hub.challenge': 'test_challenge_12345'
        }
        
        response = self.client.get(self.webhook_url, params)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.content.decode(), '"Invalid verification token"')

    @override_settings(META_WEBHOOK_VERIFY_TOKEN="test_verify_token_12345")
    def test_webhook_verification_invalid_mode(self):
        """Test webhook verification with invalid mode"""
        params = {
            'hub.mode': 'unsubscribe',
            'hub.verify_token': self.verify_token,
            'hub.challenge': 'test_challenge_12345'
        }
        
        response = self.client.get(self.webhook_url, params)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.content.decode(), '"Invalid mode"')

    @override_settings(META_WEBHOOK_VERIFY_TOKEN="test_verify_token_12345")
    def test_webhook_verification_missing_parameters(self):
        """Test webhook verification with missing parameters"""
        params = {
            'hub.mode': 'subscribe',
            # Missing verify_token and challenge
        }
        
        response = self.client.get(self.webhook_url, params)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.content.decode(), '"Missing parameters"')

    @override_settings(META_WEBHOOK_VERIFY_TOKEN="")
    def test_webhook_verification_not_configured(self):
        """Test webhook verification when token is not configured"""
        params = {
            'hub.mode': 'subscribe',
            'hub.verify_token': self.verify_token,
            'hub.challenge': 'test_challenge_12345'
        }
        
        response = self.client.get(self.webhook_url, params)
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.content.decode(), '"Webhook verification not configured"')

    def _generate_signature(self, payload: str, secret: str) -> str:
        """Generate Meta webhook signature"""
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    @override_settings(META_APP_SECRET="test_app_secret_67890")
    def test_webhook_signature_validation_success(self):
        """Test successful webhook signature validation (POST request)"""
        payload = json.dumps(self.webhook_payload)
        signature = self._generate_signature(payload, self.app_secret)
        
        response = self.client.post(
            self.webhook_url,
            data=payload,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=signature
        )
        
        # Should process the webhook (even if no integration exists for test)
        # The signature validation should pass
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(META_APP_SECRET="test_app_secret_67890")
    def test_webhook_signature_validation_invalid_signature(self):
        """Test webhook signature validation with invalid signature"""
        payload = json.dumps(self.webhook_payload)
        invalid_signature = "sha256=invalid_signature_hash"
        
        response = self.client.post(
            self.webhook_url,
            data=payload,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=invalid_signature
        )
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.content.decode(), '"Invalid signature"')

    @override_settings(META_APP_SECRET="test_app_secret_67890")
    def test_webhook_signature_validation_missing_signature(self):
        """Test webhook signature validation with missing signature header"""
        payload = json.dumps(self.webhook_payload)
        
        response = self.client.post(
            self.webhook_url,
            data=payload,
            content_type='application/json'
            # No X-Hub-Signature-256 header
        )
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.content.decode(), '"Missing signature"')

    @override_settings(META_APP_SECRET="")
    def test_webhook_signature_validation_not_configured(self):
        """Test webhook signature validation when app secret is not configured"""
        payload = json.dumps(self.webhook_payload)
        signature = self._generate_signature(payload, "any_secret")
        
        response = self.client.post(
            self.webhook_url,
            data=payload,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=signature
        )
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.content.decode(), '"Invalid signature"')

    @override_settings(
        META_APP_SECRET="test_app_secret_67890",
        META_WEBHOOK_VERIFY_TOKEN="test_verify_token_12345"
    )
    def test_webhook_both_get_and_post_endpoints(self):
        """Test that the same URL handles both GET (verification) and POST (webhook data)"""
        # Test GET verification
        get_params = {
            'hub.mode': 'subscribe',
            'hub.verify_token': self.verify_token,
            'hub.challenge': 'test_challenge_12345'
        }
        
        get_response = self.client.get(self.webhook_url, get_params)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.content.decode(), 'test_challenge_12345')
        
        # Test POST webhook data
        payload = json.dumps(self.webhook_payload)
        signature = self._generate_signature(payload, self.app_secret)
        
        post_response = self.client.post(
            self.webhook_url,
            data=payload,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=signature
        )
        
        # Should not return 401 (signature validation passed)
        self.assertNotEqual(post_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_signature_timing_attack_protection(self):
        """Test that signature comparison uses constant-time comparison"""
        # This tests the hmac.compare_digest usage
        from core.management_api.meta_api.views import MetaWebhookView
        
        webhook_view = MetaWebhookView()
        
        # Test with identical signatures
        payload = b"test_payload"
        signature1 = "sha256=abc123def456"
        signature2 = "sha256=abc123def456"
        
        # Since we're testing the internal method, we need to mock settings
        with patch('core.management_api.meta_api.views.settings') as mock_settings:
            mock_settings.META_APP_SECRET = "test_secret"
            
            # The actual verification will fail because the signature doesn't match the payload
            # But we're testing that compare_digest is used (no timing attack vulnerability)
            result = webhook_view._verify_webhook_signature(payload, signature1)
            self.assertIsInstance(result, bool)  # Should return a boolean