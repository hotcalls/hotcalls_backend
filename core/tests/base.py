"""
Base test setup for all API tests.
Provides common utilities for authentication, user creation, and test data setup.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from core.models import (
    User, Plan, Feature, PlanFeature, Workspace, Agent, PhoneNumber,
    Lead, Blacklist, CallLog, Calendar, CalendarConfiguration
)
import uuid
from datetime import time, datetime, timedelta
import json

User = get_user_model()


class BaseAPITestCase(TestCase):
    """Base test case with common setup for all API tests"""
    
    def setUp(self):
        """Set up test data and clients"""
        super().setUp()
        
        # Create API clients
        self.client = APIClient()
        self.admin_client = APIClient()
        self.staff_client = APIClient()
        self.user_client = APIClient()
        
        # Create test users
        self.admin_user = self.create_admin_user()
        self.staff_user = self.create_staff_user()
        self.regular_user = self.create_regular_user()
        
        # Authenticate clients
        self.admin_client.force_authenticate(user=self.admin_user)
        self.staff_client.force_authenticate(user=self.staff_user)
        self.user_client.force_authenticate(user=self.regular_user)
        
        # Base URLs
        self.base_url = '/api'
        
    def create_admin_user(self):
        """Create a superuser for testing"""
        return User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            phone='+1234567890'
        )
    
    def create_staff_user(self):
        """Create a staff user for testing"""
        return User.objects.create_user(
            username='staff',
            email='staff@test.com',
            password='testpass123',
            phone='+1234567891',
            is_staff=True
        )
    
    def create_regular_user(self):
        """Create a regular user for testing"""
        return User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123',
            phone='+1234567892'
        )
    
    def create_test_plan(self, name="Test Plan"):
        """Create a test plan"""
        return Plan.objects.create(plan_name=name)
    
    def create_test_feature(self, name="Test Feature"):
        """Create a test feature"""
        return Feature.objects.create(
            feature_name=name,
            description=f"Description for {name}"
        )
    
    def create_test_workspace(self, name="Test Workspace", users=None):
        """Create a test workspace"""
        workspace = Workspace.objects.create(workspace_name=name)
        if users:
            workspace.users.set(users)
        return workspace
    
    def create_test_voice(self, provider="openai", voice_external_id=None):
        """Create a test voice"""
        from core.models import Voice
        if not voice_external_id:
            voice_external_id = f"voice-{uuid.uuid4().hex[:8]}"
        
        return Voice.objects.create(
            provider=provider,
            voice_external_id=voice_external_id
        )
    
    def create_test_agent(self, workspace=None, name=None, voice=None):
        """Create a test agent"""
        if not workspace:
            workspace = self.create_test_workspace()
        
        if not name:
            name = f"Test Agent {uuid.uuid4().hex[:6]}"
        
        if voice is None:
            voice = self.create_test_voice()
        
        return Agent.objects.create(
            workspace=workspace,
            name=name,
            status='active',
            greeting_inbound="Hello, this is a test agent for inbound calls",
            greeting_outbound="Hello, this is a test agent for outbound calls", 
            voice=voice,
            language="en-US",
            retry_interval=30,
            workdays=["monday", "tuesday", "wednesday", "thursday", "friday"],
            call_from=time(9, 0),
            call_to=time(17, 0),
            character="Professional and helpful AI assistant"
        )
    
    def create_test_phone_number(self, number=None):
        """Create a test phone number"""
        if not number:
            number = f"+1555{uuid.uuid4().hex[:7]}"
        return PhoneNumber.objects.create(phonenumber=number)
    
    def create_test_lead(self, name="Test Lead", phone=None):
        """Create a test lead"""
        if not phone:
            phone = f"+1555{uuid.uuid4().hex[:7]}"
        
        return Lead.objects.create(
            name=name,
            surname="Surname",
            email=f"{name.lower().replace(' ', '')}@test.com",
            phone=phone,
            meta_data={"source": "test", "tags": ["test"]}
        )
    
    def create_test_call_log(self, lead=None, agent=None, duration=120, **kwargs):
        """Create a test call log with required agent field"""
        if not lead:
            lead = self.create_test_lead()
        
        if not agent:
            # Create a default workspace and agent for the call log
            workspace = self.create_test_workspace()
            agent = self.create_test_agent(workspace)
        
        call_data = {
            'lead': lead,
            'agent': agent,
            'from_number': kwargs.get('from_number', "+15551234567"),
            'to_number': kwargs.get('to_number', lead.phone),
            'duration': duration,
            'direction': kwargs.get('direction', "outbound"),
            'disconnection_reason': kwargs.get('disconnection_reason', "completed"),
            'status': kwargs.get('status'),
            'appointment_datetime': kwargs.get('appointment_datetime')
        }
        
        return CallLog.objects.create(**call_data)
    
    def create_test_call_log_with_appointment(self, lead=None, agent=None, appointment_datetime=None):
        """Create a test call log with an appointment scheduled"""
        if not appointment_datetime:
            from django.utils import timezone
            appointment_datetime = timezone.now() + timedelta(days=1)
        
        return self.create_test_call_log(
            lead=lead,
            agent=agent,
            status='appointment_scheduled',
            appointment_datetime=appointment_datetime
        )
    
    def create_test_call_log_with_status(self, status, lead=None, agent=None, **kwargs):
        """Create a test call log with a specific status"""
        if status == 'appointment_scheduled' and 'appointment_datetime' not in kwargs:
            from django.utils import timezone
            kwargs['appointment_datetime'] = timezone.now() + timedelta(days=1)
        
        return self.create_test_call_log(
            lead=lead,
            agent=agent,
            status=status,
            **kwargs
        )
    
    def create_test_calendar(self, workspace=None):
        """Create a test calendar"""
        if not workspace:
            workspace = self.create_test_workspace()
        
        return Calendar.objects.create(
            workspace=workspace,
            calendar_type="google",
            account_id="test@gmail.com",
            auth_token="test-auth-token"
        )
    
    def create_test_calendar_configuration(self, calendar=None):
        """Create a test calendar configuration"""
        if not calendar:
            calendar = self.create_test_calendar()
        
        return CalendarConfiguration.objects.create(
            calendar=calendar,
            sub_calendar_id="primary",
            duration=30,
            prep_time=15,
            days_buffer=1,
            from_time=time(9, 0),
            to_time=time(17, 0),
            workdays=["monday", "tuesday", "wednesday", "thursday", "friday"]
        )
    
    def assert_response_success(self, response, expected_status=status.HTTP_200_OK):
        """Assert that response was successful"""
        self.assertEqual(
            response.status_code, 
            expected_status,
            f"Expected status {expected_status}, got {response.status_code}. "
            f"Response: {response.data if hasattr(response, 'data') else response.content}"
        )
    
    def assert_delete_success(self, response):
        """Assert that DELETE operation was successful (204 No Content)"""
        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
            f"Expected status 204 for DELETE, got {response.status_code}. "
            f"Response: {response.data if hasattr(response, 'data') else response.content}"
        )
    
    def assert_response_error(self, response, expected_status):
        """Assert that response was an error"""
        self.assertEqual(
            response.status_code,
            expected_status,
            f"Expected error status {expected_status}, got {response.status_code}. "
            f"Response: {response.data if hasattr(response, 'data') else response.content}"
        )
    
    def assert_pagination_response(self, response):
        """Assert that response has pagination structure"""
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)
    
    def assert_validation_error(self, response, field=None):
        """Assert validation error response"""
        self.assert_response_error(response, status.HTTP_400_BAD_REQUEST)
        if field:
            self.assertIn(field, response.data) 