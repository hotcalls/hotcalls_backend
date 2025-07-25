"""
Comprehensive tests for Call Management API endpoints.
Tests all CRUD operations, analytics, daily statistics, duration distribution, and new features.
"""
from rest_framework import status
from core.tests.base import BaseAPITestCase
from core.models import CallLog, Lead, Agent, Workspace
import uuid
from datetime import datetime, timedelta, time
from django.utils import timezone


class CallAPITestCase(BaseAPITestCase):
    """Test cases for Call API endpoints"""
    
    def setUp(self):
        super().setUp()
        self.call_logs_url = f"{self.base_url}/calls/call-logs/"
        
        # Create test data with agents
        self.test_workspace = self.create_test_workspace("Test Workspace")
        self.test_agent = self.create_test_agent(self.test_workspace)
        self.test_lead = self.create_test_lead("Test Lead")
        self.test_call = self.create_test_call_log(self.test_lead, self.test_agent)
        
    # ========== CALL LOG LIST TESTS ==========
    
    def test_list_call_logs_authenticated(self):
        """Test authenticated users can list call logs"""
        # Create additional call logs
        lead2 = self.create_test_lead("Lead 2")
        self.create_test_call_log(lead2, self.test_agent, duration=180)
        self.create_test_call_log(self.test_lead, self.test_agent, duration=90)
        
        response = self.user_client.get(self.call_logs_url)
        self.assert_response_success(response)
        self.assert_pagination_response(response)
        self.assertGreaterEqual(response.data['count'], 3)
        
        # Check new fields are present
        first_call = response.data['results'][0]
        self.assertIn('agent', first_call)
        self.assertIn('agent_workspace_name', first_call)
        self.assertIn('status', first_call)
        self.assertIn('appointment_datetime', first_call)
    
    def test_list_call_logs_unauthenticated(self):
        """Test unauthenticated users cannot list call logs"""
        response = self.client.get(self.call_logs_url)
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_list_call_logs_with_filters(self):
        """Test filtering call logs"""
        # Create calls with different attributes
        agent2 = self.create_test_agent(self.test_workspace)
        lead2 = self.create_test_lead("Filter Lead")
        inbound_call = self.create_test_call_log(
            lead=lead2,
            agent=agent2,
            from_number="+15559876543",
            to_number="+15551234567",
            duration=150,
            direction="inbound"
        )
        
        # Filter by lead
        response = self.user_client.get(f"{self.call_logs_url}?lead={self.test_lead.id}")
        self.assert_response_success(response)
        for call in response.data['results']:
            self.assertEqual(str(call['lead']), str(self.test_lead.id))
        
        # Filter by agent
        response = self.user_client.get(f"{self.call_logs_url}?agent={agent2.agent_id}")
        self.assert_response_success(response)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(str(response.data['results'][0]['agent']), str(agent2.agent_id))
        
        # Filter by direction
        response = self.user_client.get(f"{self.call_logs_url}?direction=inbound")
        self.assert_response_success(response)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['direction'], 'inbound')
    
    def test_list_call_logs_with_status_filter(self):
        """Test filtering call logs by status"""
        # Create calls with different statuses
        self.create_test_call_log_with_status('reached', self.test_lead, self.test_agent)
        self.create_test_call_log_with_status('not_reached', self.test_lead, self.test_agent)
        self.create_test_call_log_with_appointment(self.test_lead, self.test_agent)
        
        # Filter by status
        response = self.user_client.get(f"{self.call_logs_url}?status=reached")
        self.assert_response_success(response)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'reached')
        
        # Filter by appointment_scheduled (appointments)
        response = self.user_client.get(f"{self.call_logs_url}?status=appointment_scheduled")
        self.assert_response_success(response)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'appointment_scheduled')
        self.assertIsNotNone(response.data['results'][0]['appointment_datetime'])
    
    def test_list_call_logs_with_appointment_filter(self):
        """Test filtering call logs by appointment presence"""
        # Create calls with and without appointments
        self.create_test_call_log_with_appointment(self.test_lead, self.test_agent)
        self.create_test_call_log_with_status('reached', self.test_lead, self.test_agent)
        
        # Filter calls with appointments
        response = self.user_client.get(f"{self.call_logs_url}?has_appointment=true")
        self.assert_response_success(response)
        self.assertEqual(response.data['count'], 1)
        self.assertIsNotNone(response.data['results'][0]['appointment_datetime'])
        
        # Filter calls without appointments
        response = self.user_client.get(f"{self.call_logs_url}?has_appointment=false")
        self.assert_response_success(response)
        # Should have at least the original test call and the 'erreicht' call
        self.assertGreaterEqual(response.data['count'], 2)
    
    def test_list_call_logs_with_search(self):
        """Test searching call logs by phone numbers and agent workspace"""
        unique_call = self.create_test_call_log(
            lead=self.test_lead,
            agent=self.test_agent,
            from_number="+19998887777",
            to_number="+18887776666",
            duration=200,
            direction="outbound"
        )
        
        # Search by from_number
        response = self.user_client.get(f"{self.call_logs_url}?search=9998887777")
        self.assert_response_success(response)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['from_number'], '+19998887777')
        
        # Search by workspace name
        response = self.user_client.get(f"{self.call_logs_url}?search=Test Workspace")
        self.assert_response_success(response)
        self.assertGreaterEqual(response.data['count'], 1)
    
    def test_list_call_logs_with_ordering(self):
        """Test ordering call logs"""
        # Create calls with different durations and statuses
        self.create_test_call_log(self.test_lead, self.test_agent, duration=30)
        self.create_test_call_log(self.test_lead, self.test_agent, duration=300)
        self.create_test_call_log_with_appointment(self.test_lead, self.test_agent)
        
        # Order by duration ascending
        response = self.user_client.get(f"{self.call_logs_url}?ordering=duration")
        self.assert_response_success(response)
        results = response.data['results']
        self.assertEqual(results[0]['duration'], 30)
        
        # Order by status
        response = self.user_client.get(f"{self.call_logs_url}?ordering=status")
        self.assert_response_success(response)
        
        # Order by appointment_datetime
        response = self.user_client.get(f"{self.call_logs_url}?ordering=appointment_datetime")
        self.assert_response_success(response)
    
    def test_list_call_logs_date_filtering(self):
        """Test filtering by date range"""
        # Create calls on different dates
        old_call = self.create_test_call_log(
            lead=self.test_lead,
            agent=self.test_agent,
            from_number="+15551234567",
            to_number=self.test_lead.phone,
            duration=100,
            direction="outbound"
        )
        # Set to 10 days ago
        old_date = timezone.now() - timedelta(days=10)
        CallLog.objects.filter(id=old_call.id).update(timestamp=old_date)
        
        # Filter by date
        start_date = (timezone.now() - timedelta(days=5)).date()
        response = self.user_client.get(f"{self.call_logs_url}?timestamp_after={start_date}")
        self.assert_response_success(response)
        
        # Old call should not be in results
        call_ids = [call['id'] for call in response.data['results']]
        self.assertNotIn(str(old_call.id), call_ids)
    
    # ========== CALL LOG CREATE TESTS ==========
    
    def test_create_call_log_as_admin(self):
        """Test admin can create call logs"""
        call_data = {
            'lead': str(self.test_lead.id),
            'agent': str(self.test_agent.agent_id),
            'from_number': '+15551112222',
            'to_number': '+15553334444',
            'duration': 245,
            'direction': 'outbound',
            'disconnection_reason': 'completed'
        }
        
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['duration'], 245)
        self.assertEqual(response.data['direction'], 'outbound')
        self.assertEqual(str(response.data['agent']), str(self.test_agent.agent_id))
        self.assertTrue(CallLog.objects.filter(from_number='+15551112222').exists())
    
    def test_create_call_log_with_appointment(self):
        """Test creating call log with appointment"""
        appointment_time = timezone.now() + timedelta(days=2)
        call_data = {
            'lead': str(self.test_lead.id),
            'agent': str(self.test_agent.agent_id),
            'from_number': '+15551112222',
            'to_number': '+15553334444',
            'duration': 245,
            'direction': 'outbound',
            'status': 'appointment_scheduled',
            'appointment_datetime': appointment_time.isoformat()
        }
        
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'appointment_scheduled')
        self.assertIsNotNone(response.data['appointment_datetime'])
    
    def test_create_call_log_appointment_validation(self):
        """Test appointment datetime validation"""
        # Test appointment_scheduled without appointment_datetime should fail
        call_data = {
            'lead': str(self.test_lead.id),
            'agent': str(self.test_agent.agent_id),
            'from_number': '+15551112222',
            'to_number': '+15553334444',
            'duration': 245,
            'direction': 'outbound',
            'status': 'appointment_scheduled'
        }
        
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_validation_error(response)
        self.assertIn('appointment_datetime', response.data)
        
        # Test non-appointment_scheduled with appointment_datetime should fail
        call_data = {
            'lead': str(self.test_lead.id),
            'agent': str(self.test_agent.agent_id),
            'from_number': '+15551112222',
            'to_number': '+15553334444',
            'duration': 245,
            'direction': 'outbound',
            'status': 'reached',
            'appointment_datetime': timezone.now().isoformat()
        }
        
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_validation_error(response)
        self.assertIn('appointment_datetime', response.data)
    
    def test_create_call_log_as_regular_user(self):
        """Test regular user cannot create call logs"""
        call_data = {
            'lead': str(self.test_lead.id),
            'agent': str(self.test_agent.agent_id),
            'from_number': '+15555556666',
            'to_number': '+15557778888',
            'duration': 180,
            'direction': 'inbound'
        }
        
        response = self.user_client.post(self.call_logs_url, call_data, format='json')
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_create_call_log_validation(self):
        """Test call log creation validation"""
        # Missing required fields (including agent)
        response = self.admin_client.post(self.call_logs_url, {}, format='json')
        self.assert_validation_error(response)
        required_fields = ['lead', 'agent', 'from_number', 'to_number', 'duration', 'direction']
        for field in required_fields:
            self.assertIn(field, response.data)
        
        # Invalid direction
        call_data = {
            'lead': str(self.test_lead.id),
            'agent': str(self.test_agent.agent_id),
            'from_number': '+15551234567',
            'to_number': '+15559876543',
            'duration': 100,
            'direction': 'invalid_direction'
        }
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_validation_error(response)
        self.assertIn('direction', response.data)
        
        # Invalid status
        call_data['direction'] = 'outbound'
        call_data['status'] = 'invalid_status'
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_validation_error(response)
        self.assertIn('status', response.data)
        
        # Negative duration
        call_data['status'] = 'reached'
        call_data['duration'] = -10
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_validation_error(response)
        self.assertIn('duration', response.data)
    
    def test_create_call_log_without_agent_fails(self):
        """Test creating call log without agent fails"""
        call_data = {
            'lead': str(self.test_lead.id),
            'from_number': '+15551234567',
            'to_number': '+15559876543',
            'duration': 120,
            'direction': 'outbound'
        }
        
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_validation_error(response)
        self.assertIn('agent', response.data)
    
    # ========== CALL LOG RETRIEVE TESTS ==========
    
    def test_retrieve_call_log(self):
        """Test retrieving single call log"""
        response = self.user_client.get(f"{self.call_logs_url}{self.test_call.id}/")
        self.assert_response_success(response)
        self.assertEqual(str(response.data['id']), str(self.test_call.id))
        self.assertEqual(str(response.data['lead']), str(self.test_lead.id))
        self.assertEqual(str(response.data['agent']), str(self.test_agent.agent_id))
        self.assertIn('agent_workspace_name', response.data)
        self.assertIn('timestamp', response.data)
        self.assertIn('status', response.data)
        self.assertIn('appointment_datetime', response.data)
    
    def test_retrieve_nonexistent_call_log(self):
        """Test retrieving non-existent call log"""
        fake_id = str(uuid.uuid4())
        response = self.user_client.get(f"{self.call_logs_url}{fake_id}/")
        self.assert_response_error(response, status.HTTP_404_NOT_FOUND)
    
    # ========== CALL LOG UPDATE TESTS ==========
    
    def test_update_call_log_as_admin(self):
        """Test admin can update call logs"""
        response = self.admin_client.patch(
            f"{self.call_logs_url}{self.test_call.id}/",
            {
                'duration': 300,
                'disconnection_reason': 'customer_hangup',
                'status': 'reached'
            },
            format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['duration'], 300)
        self.assertEqual(response.data['disconnection_reason'], 'customer_hangup')
        self.assertEqual(response.data['status'], 'reached')
    
    def test_update_call_log_appointment_logic(self):
        """Test updating call log with appointment validation"""
        # Update to appointment_scheduled with appointment
        appointment_time = timezone.now() + timedelta(days=1)
        response = self.admin_client.patch(
            f"{self.call_logs_url}{self.test_call.id}/",
            {
                'status': 'appointment_scheduled',
                'appointment_datetime': appointment_time.isoformat()
            },
            format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['status'], 'appointment_scheduled')
        self.assertIsNotNone(response.data['appointment_datetime'])
        
        # Update to reached should clear appointment
        response = self.admin_client.patch(
            f"{self.call_logs_url}{self.test_call.id}/",
            {
                'status': 'reached',
                'appointment_datetime': None
            },
            format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['status'], 'reached')
        self.assertIsNone(response.data['appointment_datetime'])
    
    def test_update_call_log_as_regular_user(self):
        """Test regular user cannot update call logs"""
        response = self.user_client.patch(
            f"{self.call_logs_url}{self.test_call.id}/", {'duration': 150}, format='json'
        )
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    # ========== CALL LOG DELETE TESTS ==========
    
    def test_delete_call_log_as_admin(self):
        """Test admin can delete call logs"""
        call_to_delete = self.create_test_call_log(agent=self.test_agent)
        
        response = self.admin_client.delete(f"{self.call_logs_url}{call_to_delete.id}/")
        self.assert_delete_success(response)
        self.assertFalse(CallLog.objects.filter(id=call_to_delete.id).exists())
    
    def test_delete_call_log_as_regular_user(self):
        """Test regular user cannot delete call logs"""
        call_to_delete = self.create_test_call_log(self.test_lead, self.test_agent)
        
        response = self.user_client.delete(f"{self.call_logs_url}{call_to_delete.id}/")
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    # ========== ANALYTICS TESTS ==========
    
    def test_get_call_analytics_as_admin(self):
        """Test admin can get call analytics"""
        # Create more test data with various statuses
        for i in range(5):
            lead = self.create_test_lead(f"Analytics Lead {i}")
            self.create_test_call_log_with_status('reached', lead, self.test_agent, duration=60 + i*30)
            if i < 3:  # Create some appointments
                self.create_test_call_log_with_appointment(lead, self.test_agent)
        
        response = self.admin_client.get(f"{self.call_logs_url}analytics/")
        self.assert_response_success(response)
        
        # Check analytics structure
        self.assertIn('total_calls', response.data)
        self.assertIn('total_duration', response.data)
        self.assertIn('avg_duration', response.data)
        self.assertIn('inbound_calls', response.data)
        self.assertIn('outbound_calls', response.data)
        self.assertIn('status_breakdown', response.data)
        self.assertIn('appointments_scheduled', response.data)
        self.assertIn('appointments_today', response.data)
        
        # Verify some values
        self.assertGreaterEqual(response.data['total_calls'], 0)
        self.assertGreaterEqual(response.data['total_duration'], 0)
        self.assertGreaterEqual(response.data['avg_duration'], 0)
        self.assertIsInstance(response.data['status_breakdown'], dict)
    
    def test_get_analytics_as_regular_user(self):
        """Test regular user can get analytics"""
        response = self.user_client.get(f"{self.call_logs_url}analytics/")
        self.assert_response_success(response)
    
    def test_status_analytics_endpoint(self):
        """Test status analytics endpoint"""
        # Create calls with different statuses
        statuses = ['reached', 'not_reached', 'no_interest']
        for status in statuses:
            for i in range(2):
                self.create_test_call_log_with_status(status, agent=self.test_agent)
        
        # Create appointments
        for i in range(3):
            self.create_test_call_log_with_appointment(agent=self.test_agent)
        
        response = self.admin_client.get(f"{self.call_logs_url}status_analytics/")
        self.assert_response_success(response)
        
        self.assertIn('total_calls', response.data)
        self.assertIn('status_breakdown', response.data)
        self.assertIn('success_rate', response.data)
        
        # Check status breakdown
        status_breakdown = response.data['status_breakdown']
        self.assertGreaterEqual(status_breakdown.get('reached', 0), 2)
        self.assertGreaterEqual(status_breakdown.get('appointment_scheduled', 0), 3)
    
    def test_agent_performance_endpoint(self):
        """Test agent performance analytics endpoint"""
        # Create another agent for comparison
        agent2 = self.create_test_agent(self.test_workspace)
        
        # Create calls for different agents
        for i in range(3):
            self.create_test_call_log_with_status('reached', agent=self.test_agent)
            self.create_test_call_log_with_status('not_reached', agent=agent2)
        
        # Create appointments
        self.create_test_call_log_with_appointment(agent=self.test_agent)
        
        response = self.admin_client.get(f"{self.call_logs_url}agent_performance/")
        self.assert_response_success(response)
        
        self.assertIsInstance(response.data, list)
        self.assertGreaterEqual(len(response.data), 2)  # At least 2 agents
        
        # Check agent data structure
        agent_data = response.data[0]
        self.assertIn('agent_id', agent_data)
        self.assertIn('agent_workspace', agent_data)
        self.assertIn('total_calls', agent_data)
        self.assertIn('avg_duration', agent_data)
        self.assertIn('status_breakdown', agent_data)
        self.assertIn('appointments_scheduled', agent_data)
    
    def test_appointment_stats_endpoint(self):
        """Test appointment statistics endpoint"""
        # Create appointments at different times
        today_appointment = timezone.now().replace(hour=14, minute=0, second=0, microsecond=0)
        future_appointment = timezone.now() + timedelta(days=5)
        past_appointment = timezone.now() - timedelta(days=2)
        
        self.create_test_call_log_with_appointment(appointment_datetime=today_appointment, agent=self.test_agent)
        self.create_test_call_log_with_appointment(appointment_datetime=future_appointment, agent=self.test_agent)
        self.create_test_call_log_with_appointment(appointment_datetime=past_appointment, agent=self.test_agent)
        
        response = self.admin_client.get(f"{self.call_logs_url}appointment_stats/")
        self.assert_response_success(response)
        
        self.assertIn('total_appointments', response.data)
        self.assertIn('appointments_today', response.data)
        self.assertIn('appointments_this_week', response.data)
        self.assertIn('appointments_this_month', response.data)
        self.assertIn('upcoming_appointments', response.data)
        self.assertIn('past_appointments', response.data)
        
        # Verify appointment counts
        self.assertGreaterEqual(response.data['total_appointments'], 3)
        self.assertGreaterEqual(response.data['upcoming_appointments'], 1)
        self.assertGreaterEqual(response.data['past_appointments'], 1)
    
    # ========== DAILY STATS TESTS ==========
    
    def test_get_daily_stats_as_admin(self):
        """Test admin can get daily statistics"""
        # Create calls across different days
        today = timezone.now().date()
        for i in range(7):
            call_date = today - timedelta(days=i)
            for j in range(i + 1):  # Variable calls per day
                lead = self.create_test_lead(f"Daily Lead {i}-{j}")
                call = self.create_test_call_log(
                    lead=lead,
                    agent=self.test_agent,
                    from_number="+15551234567",
                    to_number=lead.phone,
                    duration=60 + j*20,
                    direction="outbound"
                )
                # Set specific date with timezone awareness
                naive_datetime = datetime.combine(call_date, time(10, 0))
                aware_datetime = timezone.make_aware(naive_datetime)
                CallLog.objects.filter(id=call.id).update(
                    timestamp=aware_datetime
                )
        
        response = self.admin_client.get(f"{self.call_logs_url}daily_stats/")
        self.assert_response_success(response)
        
        # Check structure
        self.assertIn('daily_stats', response.data)
        daily_stats = response.data['daily_stats']
        self.assertGreater(len(daily_stats), 0)
        
        for day_stat in daily_stats:
            self.assertIn('date', day_stat)
            self.assertIn('calls', day_stat)
            self.assertIn('total_duration', day_stat)
            self.assertIn('avg_duration', day_stat)
        
        # Check dates are valid ISO format
        dates = [stat['date'] for stat in daily_stats]
        for date_str in dates:
            self.assertRegex(date_str, r'^\d{4}-\d{2}-\d{2}$')
    
    def test_daily_stats_as_regular_user(self):
        """Test regular user can get daily stats"""
        response = self.user_client.get(f"{self.call_logs_url}daily_stats/")
        self.assert_response_success(response, status.HTTP_200_OK)
    
    # ========== DURATION DISTRIBUTION TESTS ==========
    
    def test_duration_distribution_as_regular_user(self):
        """Test regular user can access duration distribution"""
        response = self.user_client.get(f"{self.call_logs_url}duration_distribution/")
        self.assert_response_success(response, status.HTTP_200_OK)
    
    def test_duration_distribution_buckets(self):
        """Test duration distribution bucket ranges"""
        # Create calls in specific duration ranges
        test_durations = [25, 45, 90, 150, 240, 400, 700]
        
        for duration in test_durations:
            lead = self.create_test_lead(f"Bucket Lead {duration}")
            self.create_test_call_log(lead, self.test_agent, duration=duration)
        
        response = self.admin_client.get(f"{self.call_logs_url}duration_distribution/")
        self.assert_response_success(response)
        
        # Check structure
        self.assertIn('duration_ranges', response.data)
        duration_ranges = response.data['duration_ranges']
        
        # Verify we have the expected ranges
        expected_ranges = ['0-30s', '31-60s', '61-120s', '121-300s', '300s+']
        for range_key in expected_ranges:
            if range_key in duration_ranges:
                count = duration_ranges[range_key].get('count', 0)
                self.assertGreaterEqual(count, 0)
    
    # ========== EDGE CASES AND BUSINESS LOGIC TESTS ==========
    
    def test_call_log_with_same_numbers(self):
        """Test creating call log where from and to numbers are the same"""
        call_data = {
            'lead': str(self.test_lead.id),
            'agent': str(self.test_agent.agent_id),
            'from_number': '+15551234567',
            'to_number': '+15551234567',  # Same as from
            'duration': 0,
            'direction': 'outbound',
            'disconnection_reason': 'invalid_number'
        }
        
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
    
    def test_call_log_with_zero_duration(self):
        """Test creating call log with zero duration"""
        call_data = {
            'lead': str(self.test_lead.id),
            'agent': str(self.test_agent.agent_id),
            'from_number': '+15551234567',
            'to_number': '+15559876543',
            'duration': 0,
            'direction': 'outbound',
            'disconnection_reason': 'no_answer'
        }
        
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['duration'], 0)
    
    def test_english_status_choices(self):
        """Test all English status choices work correctly"""
        english_statuses = ['appointment_scheduled', 'not_reached', 'no_interest', 'reached']
        
        for call_status in english_statuses:
            call_data = {
                'lead': str(self.test_lead.id),
                'agent': str(self.test_agent.agent_id),
                'from_number': '+15551234567',
                'to_number': '+15559876543',
                'duration': 120,
                'direction': 'outbound',
                'status': call_status
            }
            
            # Add appointment for appointment_scheduled
            if call_status == 'appointment_scheduled':
                call_data['appointment_datetime'] = (timezone.now() + timedelta(days=1)).isoformat()
            
            response = self.admin_client.post(self.call_logs_url, call_data, format='json')
            self.assert_response_success(response, status.HTTP_201_CREATED)
            self.assertEqual(response.data['status'], call_status)
    
    def test_appointment_in_past_allowed(self):
        """Test that appointments in the past are allowed"""
        past_appointment = timezone.now() - timedelta(days=1)
        call_data = {
            'lead': str(self.test_lead.id),
            'agent': str(self.test_agent.agent_id),
            'from_number': '+15551234567',
            'to_number': '+15559876543',
            'duration': 120,
            'direction': 'outbound',
            'status': 'appointment_scheduled',
            'appointment_datetime': past_appointment.isoformat()
        }
        
        response = self.admin_client.post(self.call_logs_url, call_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'appointment_scheduled')
        self.assertIsNotNone(response.data['appointment_datetime'])
    
    def test_appointment_scheduling_workflow(self):
        """Test complete appointment scheduling workflow"""
        # 1. Create initial call without appointment
        call = self.create_test_call_log(self.test_lead, self.test_agent)
        
        # 2. Update to schedule appointment
        appointment_time = timezone.now() + timedelta(days=2)
        response = self.admin_client.patch(
            f"{self.call_logs_url}{call.id}/",
            {
                'status': 'appointment_scheduled',
                'appointment_datetime': appointment_time.isoformat()
            },
            format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['status'], 'appointment_scheduled')
        
        # 3. Verify in analytics
        response = self.admin_client.get(f"{self.call_logs_url}appointment_stats/")
        self.assert_response_success(response)
        self.assertGreaterEqual(response.data['total_appointments'], 1)
        
        # 4. Update to completed status
        response = self.admin_client.patch(
            f"{self.call_logs_url}{call.id}/",
            {
                'status': 'reached',
                'appointment_datetime': None
            },
            format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['status'], 'reached')
        self.assertIsNone(response.data['appointment_datetime'])
    
    def test_bulk_call_creation_performance(self):
        """Test creating many call logs with agents"""
        # Create 50 calls quickly
        leads = [self.create_test_lead(f"Bulk Lead {i}") for i in range(10)]
        
        for i in range(50):
            lead = leads[i % 10]
            call_data = {
                'lead': str(lead.id),
                'agent': str(self.test_agent.agent_id),
                'from_number': f'+1555{i:07d}',
                'to_number': lead.phone,
                'duration': 60 + i,
                'direction': 'outbound' if i % 2 == 0 else 'inbound'
            }
            
            response = self.admin_client.post(self.call_logs_url, call_data, format='json')
            self.assert_response_success(response, status.HTTP_201_CREATED)
        
        # Verify all created
        self.assertGreaterEqual(CallLog.objects.count(), 51)  # 50 + initial
    
    def test_call_log_updated_at_changes(self):
        """Test that updated_at changes when call log is modified"""
        # Get initial updated_at
        initial_updated = self.test_call.updated_at
        
        # Wait and update
        import time
        time.sleep(0.1)
        
        response = self.admin_client.patch(
            f"{self.call_logs_url}{self.test_call.id}/", {'duration': 999}, format='json'
        )
        self.assert_response_success(response)
        
        # Verify updated_at changed
        self.test_call.refresh_from_db()
        self.assertNotEqual(self.test_call.updated_at, initial_updated) 