"""
Tests for Google Calendar integration.
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    User, Workspace, Calendar, GoogleCalendarConnection, GoogleCalendar, 
    CalendarConfiguration
)
from core.services.google_calendar import GoogleCalendarService, GoogleOAuthService, CalendarServiceFactory
from .base import BaseAPITestCase


class GoogleCalendarModelsTestCase(TestCase):
    """Test Google Calendar models"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            phone='+1234567890'
        )
        self.workspace = Workspace.objects.create(
            workspace_name='Test Workspace'
        )
        self.workspace.users.add(self.user)
    
    def test_google_calendar_connection_creation(self):
        """Test creating a Google Calendar connection"""
        connection = GoogleCalendarConnection.objects.create(
            user=self.user,
            workspace=self.workspace,
            account_email='test@gmail.com',
            refresh_token='refresh_token_123',
            access_token='access_token_123',
            token_expires_at=timezone.now() + timedelta(hours=1),
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        
        self.assertEqual(connection.user, self.user)
        self.assertEqual(connection.workspace, self.workspace)
        self.assertEqual(connection.account_email, 'test@gmail.com')
        self.assertTrue(connection.active)
        self.assertIsNone(connection.last_sync)
    
    def test_calendar_creation(self):
        """Test creating a generic calendar"""
        calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='Test Calendar',
            provider='google'
        )
        
        self.assertEqual(calendar.workspace, self.workspace)
        self.assertEqual(calendar.name, 'Test Calendar')
        self.assertEqual(calendar.provider, 'google')
        self.assertTrue(calendar.active)
    
    def test_google_calendar_creation(self):
        """Test creating Google-specific calendar metadata"""
        connection = GoogleCalendarConnection.objects.create(
            user=self.user,
            workspace=self.workspace,
            account_email='test@gmail.com',
            refresh_token='refresh_token_123',
            access_token='access_token_123',
            token_expires_at=timezone.now() + timedelta(hours=1),
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        
        calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='Test Calendar',
            provider='google'
        )
        
        google_calendar = GoogleCalendar.objects.create(
            calendar=calendar,
            connection=connection,
            external_id='test_calendar_id_123',
            summary='Test Calendar',
            primary=True,
            access_role='owner',
            time_zone='UTC'
        )
        
        self.assertEqual(google_calendar.calendar, calendar)
        self.assertEqual(google_calendar.connection, connection)
        self.assertEqual(google_calendar.external_id, 'test_calendar_id_123')
        self.assertTrue(google_calendar.primary)
        self.assertEqual(google_calendar.access_role, 'owner')
    
    def test_calendar_configuration_with_new_model(self):
        """Test calendar configuration with new normalized model"""
        calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='Test Calendar',
            provider='google'
        )
        
        config = CalendarConfiguration.objects.create(
            calendar=calendar,
            duration=60,
            prep_time=15,
            days_buffer=1,
            from_time='09:00:00',
            to_time='17:00:00',
            workdays=['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
        )
        
        self.assertEqual(config.calendar, calendar)
        self.assertEqual(config.duration, 60)
        self.assertEqual(config.prep_time, 15)
        self.assertEqual(len(config.workdays), 5)


class GoogleCalendarServiceTestCase(TestCase):
    """Test Google Calendar service layer"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com', 
            password='testpass123',
            phone='+1234567890'
        )
        self.workspace = Workspace.objects.create(
            workspace_name='Test Workspace'
        )
        self.workspace.users.add(self.user)
        
        self.connection = GoogleCalendarConnection.objects.create(
            user=self.user,
            workspace=self.workspace,
            account_email='test@gmail.com',
            refresh_token='refresh_token_123',
            access_token='access_token_123',
            token_expires_at=timezone.now() + timedelta(hours=1),
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
    
    @patch('core.services.google_calendar.build')
    @patch('core.services.google_calendar.Credentials')
    def test_google_calendar_service_initialization(self, mock_credentials, mock_build):
        """Test Google Calendar service initialization"""
        service = GoogleCalendarService(self.connection)
        self.assertEqual(service.connection, self.connection)
    
    @patch('core.services.google_calendar.build')
    @patch('core.services.google_calendar.Credentials')
    def test_sync_calendars(self, mock_credentials, mock_build):
        """Test syncing calendars from Google"""
        # Mock Google API response
        mock_service = Mock()
        mock_build.return_value = mock_service
        mock_calendar_list = Mock()
        mock_service.calendarList.return_value = mock_calendar_list
        mock_calendar_list.list.return_value.execute.return_value = {
            'items': [
                {
                    'id': 'calendar_1',
                    'summary': 'Primary Calendar',
                    'primary': True,
                    'accessRole': 'owner',
                    'timeZone': 'America/New_York',
                    'backgroundColor': '#16a085'
                },
                {
                    'id': 'calendar_2', 
                    'summary': 'Work Calendar',
                    'primary': False,
                    'accessRole': 'writer',
                    'timeZone': 'America/New_York'
                }
            ]
        }
        
        # Mock credentials
        mock_creds = Mock()
        mock_creds.expired = False
        mock_credentials.return_value = mock_creds
        
        service = GoogleCalendarService(self.connection)
        with patch.object(service, '_token_expires_soon', return_value=False):
            calendars = service.sync_calendars()
        
        # Verify calendars were created
        self.assertEqual(len(calendars), 2)
        self.assertEqual(Calendar.objects.count(), 2)
        self.assertEqual(GoogleCalendar.objects.count(), 2)
        
        # Check primary calendar
        primary_calendar = GoogleCalendar.objects.get(primary=True)
        self.assertEqual(primary_calendar.external_id, 'calendar_1')
        self.assertEqual(primary_calendar.summary, 'Primary Calendar')
        self.assertEqual(primary_calendar.access_role, 'owner')
    
    @patch('core.services.google_calendar.Flow')
    def test_oauth_token_exchange(self, mock_flow):
        """Test exchanging OAuth code for tokens"""
        # Mock OAuth flow
        mock_flow_instance = Mock()
        mock_flow.from_client_config.return_value = mock_flow_instance
        
        mock_credentials = Mock()
        mock_credentials.token = 'new_access_token'
        mock_credentials.refresh_token = 'new_refresh_token'
        mock_credentials.expiry = timezone.now() + timedelta(hours=1)
        mock_credentials.scopes = ['https://www.googleapis.com/auth/calendar.readonly']
        
        mock_flow_instance.credentials = mock_credentials
        
        credentials = GoogleOAuthService.exchange_code_for_tokens('auth_code_123')
        
        self.assertEqual(credentials.token, 'new_access_token')
        self.assertEqual(credentials.refresh_token, 'new_refresh_token')
        mock_flow_instance.fetch_token.assert_called_once_with(code='auth_code_123')
    
    def test_calendar_service_factory(self):
        """Test calendar service factory"""
        calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='Test Calendar',
            provider='google'
        )
        
        google_calendar = GoogleCalendar.objects.create(
            calendar=calendar,
            connection=self.connection,
            external_id='test_calendar_id',
            summary='Test Calendar',
            access_role='owner',
            time_zone='UTC'
        )
        
        service = CalendarServiceFactory.get_service(calendar)
        self.assertIsInstance(service, GoogleCalendarService)
        self.assertEqual(service.connection, self.connection)
        
        # Test unsupported provider
        outlook_calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='Outlook Calendar',
            provider='outlook'
        )
        
        with self.assertRaises(ValueError):
            CalendarServiceFactory.get_service(outlook_calendar)


class GoogleCalendarAPITestCase(BaseAPITestCase):
    """Test Google Calendar API endpoints"""
    
    def setUp(self):
        super().setUp()
        self.calendar_url = f'{self.base_url}/calendars/'
        
        # Create workspace for testing
        self.workspace = self.create_test_workspace(users=[self.regular_user])
    
    @patch('core.services.google_calendar.GoogleOAuthService.exchange_code_for_tokens')
    @patch('core.services.google_calendar.GoogleOAuthService.get_user_info')
    @patch('core.services.google_calendar.GoogleCalendarService.sync_calendars')
    def test_google_oauth_callback_success(self, mock_sync_calendars, mock_get_user_info, mock_exchange_tokens):
        """Test successful Google OAuth callback"""
        # Mock OAuth service responses
        mock_credentials = Mock()
        mock_credentials.refresh_token = 'refresh_token_123'
        mock_credentials.token = 'access_token_123'
        mock_credentials.expiry = timezone.now() + timedelta(hours=1)
        mock_credentials.scopes = ['https://www.googleapis.com/auth/calendar.readonly']
        mock_exchange_tokens.return_value = mock_credentials
        
        mock_get_user_info.return_value = {
            'email': 'test@gmail.com',
            'name': 'Test User',
            'verified_email': True
        }
        
        # Mock calendar sync
        calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='Test Calendar',
            provider='google'
        )
        mock_sync_calendars.return_value = [calendar]
        
        # Make OAuth callback request
        url = f'{self.calendar_url}google_callback/'
        response = self.user_client.get(url, {'code': 'auth_code_123'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['connection']['account_email'], 'test@gmail.com')
        self.assertEqual(len(response.data['calendars']), 1)
        
        # Verify connection was created
        self.assertTrue(GoogleCalendarConnection.objects.filter(account_email='test@gmail.com').exists())
    
    def test_google_oauth_callback_missing_code(self):
        """Test OAuth callback with missing authorization code"""
        url = f'{self.calendar_url}google_callback/'
        response = self.user_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No authorization code received', response.data['error'])
    
    def test_google_oauth_callback_error(self):
        """Test OAuth callback with error parameter"""
        url = f'{self.calendar_url}google_callback/'
        response = self.user_client.get(url, {'error': 'access_denied'})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('access_denied', response.data['error'])
    
    def test_list_google_connections(self):
        """Test listing Google Calendar connections"""
        connection = GoogleCalendarConnection.objects.create(
            user=self.regular_user,
            workspace=self.workspace,
            account_email='test@gmail.com',
            refresh_token='refresh_token_123',
            access_token='access_token_123',
            token_expires_at=timezone.now() + timedelta(hours=1),
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        
        url = f'{self.calendar_url}google_connections/'
        response = self.user_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['account_email'], 'test@gmail.com')
    
    @patch('core.services.google_calendar.GoogleCalendarService.test_connection')
    @patch('core.services.google_calendar.GoogleCalendarService.sync_calendars')
    def test_refresh_google_connection(self, mock_sync_calendars, mock_test_connection):
        """Test refreshing a Google Calendar connection"""
        connection = GoogleCalendarConnection.objects.create(
            user=self.regular_user,
            workspace=self.workspace,
            account_email='test@gmail.com',
            refresh_token='refresh_token_123',
            access_token='access_token_123',
            token_expires_at=timezone.now() + timedelta(hours=1),
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        
        # Mock service responses
        mock_test_connection.return_value = {'success': True}
        mock_sync_calendars.return_value = []
        
        url = f'{self.calendar_url}{connection.id}/google_refresh/'
        response = self.user_client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        mock_test_connection.assert_called_once()
        mock_sync_calendars.assert_called_once()
    
    @patch('core.services.google_calendar.GoogleOAuthService.revoke_token')
    def test_disconnect_google_connection(self, mock_revoke_token):
        """Test disconnecting a Google Calendar connection"""
        connection = GoogleCalendarConnection.objects.create(
            user=self.regular_user,
            workspace=self.workspace,
            account_email='test@gmail.com',
            refresh_token='refresh_token_123',
            access_token='access_token_123',
            token_expires_at=timezone.now() + timedelta(hours=1),
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        
        mock_revoke_token.return_value = True
        
        url = f'{self.calendar_url}{connection.id}/google_disconnect/'
        response = self.user_client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        # Verify connection was deactivated
        connection.refresh_from_db()
        self.assertFalse(connection.active)
    
    @patch('core.services.google_calendar.GoogleCalendarService.check_availability')
    def test_real_availability_checking(self, mock_check_availability):
        """Test real availability checking with Google Calendar API"""
        # Create calendar structure
        connection = GoogleCalendarConnection.objects.create(
            user=self.regular_user,
            workspace=self.workspace,
            account_email='test@gmail.com',
            refresh_token='refresh_token_123',
            access_token='access_token_123',
            token_expires_at=timezone.now() + timedelta(hours=1),
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        
        calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='Test Calendar',
            provider='google'
        )
        
        google_calendar = GoogleCalendar.objects.create(
            calendar=calendar,
            connection=connection,
            external_id='test_calendar_id',
            summary='Test Calendar',
            access_role='owner',
            time_zone='UTC'
        )
        
        config = CalendarConfiguration.objects.create(
            calendar=calendar,
            duration=60,
            prep_time=15,
            from_time='09:00:00',
            to_time='17:00:00',
            workdays=['monday', 'tuesday', 'wednesday']
        )
        
        # Mock Google API response
        mock_check_availability.return_value = [
            {
                'start': '2024-01-15T10:00:00Z',
                'end': '2024-01-15T11:00:00Z'
            }
        ]
        
        url = f'{self.base_url}/calendar-configurations/{config.id}/check_availability/'
        data = {
            'date': '2024-01-15',
            'duration_minutes': 60
        }
        
        response = self.user_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('available_slots', response.data)
        self.assertIn('busy_times', response.data)
        mock_check_availability.assert_called_once()


class GoogleCalendarTasksTestCase(TestCase):
    """Test Celery tasks for Google Calendar integration"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            phone='+1234567890'
        )
        self.workspace = Workspace.objects.create(
            workspace_name='Test Workspace'
        )
        
        # Create connection with expiring token
        self.connection = GoogleCalendarConnection.objects.create(
            user=self.user,
            workspace=self.workspace,
            account_email='test@gmail.com',
            refresh_token='refresh_token_123',
            access_token='access_token_123',
            token_expires_at=timezone.now() + timedelta(minutes=3),  # Expires soon
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
    
    @patch('core.services.google_calendar.GoogleCalendarService.test_connection')
    @patch('core.tasks.sync_google_calendars.delay')
    def test_refresh_google_calendar_connections_task(self, mock_sync_task, mock_test_connection):
        """Test the periodic token refresh task"""
        from core.tasks import refresh_google_calendar_connections
        
        mock_test_connection.return_value = {'success': True}
        
        result = refresh_google_calendar_connections()
        
        self.assertEqual(result['total_connections'], 1)
        self.assertEqual(result['refreshed'], 1)
        mock_test_connection.assert_called_once()
        mock_sync_task.assert_called_once_with(self.connection.id)
    
    @patch('core.services.google_calendar.GoogleCalendarService.sync_calendars')
    def test_sync_google_calendars_task(self, mock_sync_calendars):
        """Test the calendar sync task"""
        from core.tasks import sync_google_calendars
        
        # Mock sync response
        calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='Test Calendar',
            provider='google'
        )
        mock_sync_calendars.return_value = [calendar]
        
        result = sync_google_calendars(self.connection.id)
        
        self.assertEqual(str(result['connection_id']), str(self.connection.id))
        self.assertEqual(result['calendars_synced'], 1)
        mock_sync_calendars.assert_called_once()
    
    def test_sync_google_calendars_task_connection_not_found(self):
        """Test sync task with non-existent connection"""
        from core.tasks import sync_google_calendars
        
        fake_id = uuid.uuid4()
        result = sync_google_calendars(fake_id)
        
        self.assertIn('error', result)
        self.assertEqual(str(result['connection_id']), str(fake_id))


class CalendarPermissionsTestCase(BaseAPITestCase):
    """Test calendar permissions with new model structure"""
    
    def setUp(self):
        super().setUp()
        # Create workspace for testing
        self.workspace = self.create_test_workspace(users=[self.regular_user])
        self.calendar_url = f'{self.base_url}/calendars/'
    
    def test_regular_user_calendar_access(self):
        """Test that regular users can only access their workspace calendars"""
        # Create calendar in user's workspace
        user_calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='User Calendar',
            provider='google'
        )
        
        # Create calendar in different workspace
        other_workspace = Workspace.objects.create(workspace_name='Other Workspace')
        other_calendar = Calendar.objects.create(
            workspace=other_workspace,
            name='Other Calendar',
            provider='google'
        )
        
        url = f'{self.calendar_url}'
        response = self.user_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # User should only see their workspace calendar
        if isinstance(response.data, list):
            results = response.data
        elif isinstance(response.data, dict) and 'results' in response.data:
            results = response.data['results']
        else:
            results = []
        calendar_ids = [cal['id'] for cal in results]
        self.assertIn(str(user_calendar.id), calendar_ids)
        self.assertNotIn(str(other_calendar.id), calendar_ids)
    
    def test_staff_user_calendar_access(self):
        """Test that staff users can access all calendars"""
        # Create calendars in different workspaces
        user_calendar = Calendar.objects.create(
            workspace=self.workspace,
            name='User Calendar',
            provider='google'
        )
        
        other_workspace = Workspace.objects.create(workspace_name='Other Workspace')
        other_calendar = Calendar.objects.create(
            workspace=other_workspace,
            name='Other Calendar',
            provider='google'
        )
        
        url = f'{self.calendar_url}'
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Staff should see all calendars
        if isinstance(response.data, list):
            results = response.data
        elif isinstance(response.data, dict) and 'results' in response.data:
            results = response.data['results']
        else:
            results = []
        calendar_ids = [cal['id'] for cal in results]
        self.assertIn(str(user_calendar.id), calendar_ids)
        self.assertIn(str(other_calendar.id), calendar_ids) 