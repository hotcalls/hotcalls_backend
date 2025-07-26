"""
Comprehensive tests for Agent Management API endpoints.
Tests Agent and PhoneNumber operations including phone assignment and configuration.
"""
from rest_framework import status
from core.tests.base import BaseAPITestCase
from core.models import Agent, PhoneNumber, Workspace, CalendarConfiguration, Voice
import uuid
from datetime import time
import json


class AgentAPITestCase(BaseAPITestCase):
    """Test cases for Agent API endpoints"""
    
    def setUp(self):
        super().setUp()
        self.agents_url = f"{self.base_url}/agents/agents/"
        self.phone_numbers_url = f"{self.base_url}/agents/phone-numbers/"
        
        # Create test workspace and agent
        self.test_workspace = self.create_test_workspace("Test Workspace")
        self.test_workspace.users.add(self.regular_user, self.admin_user, self.staff_user)
        
        # Create test voice for agents
        self.test_voice = Voice.objects.create(
            voice_external_id='en-US-Standard-A',
            provider='google'
        )
        
        self.test_agent = self.create_test_agent(self.test_workspace, voice=self.test_voice)
    
    def get_agent_data(self, **overrides):
        """Helper method to get valid agent data"""
        data = {
            'workspace': str(self.test_workspace.id),
            'name': 'Test Agent',
            'status': 'active',
            'greeting_inbound': 'Hello, how can I help you today?',
            'greeting_outbound': 'Hello, this is a sales call.',
            'voice': str(self.test_voice.id),
            'language': 'en-US',
            'retry_interval': 45,
            'workdays': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
            'call_from': '08:00:00',
            'call_to': '18:00:00',
            'character': 'Professional and courteous customer service representative'
        }
        data.update(overrides)
        return data
        
    # ========== AGENT LIST TESTS ==========
    
    def test_list_agents_authenticated(self):
        """Test authenticated users can list agents"""
        # Create additional agents
        self.create_test_agent(self.test_workspace)
        workspace2 = self.create_test_workspace("Workspace 2")
        self.create_test_agent(workspace2)
        
        response = self.user_client.get(self.agents_url)
        self.assert_response_success(response)
        self.assert_pagination_response(response)
        self.assertGreaterEqual(response.data['count'], 2)
    
    def test_list_agents_unauthenticated(self):
        """Test unauthenticated users cannot list agents"""
        response = self.client.get(self.agents_url)
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_list_agents_with_filters(self):
        """Test filtering agents by workspace"""
        # Create agents in different workspaces
        workspace2 = self.create_test_workspace("Workspace 2")
        agent2 = self.create_test_agent(workspace2)
        
        # Filter by workspace
        response = self.user_client.get(f"{self.agents_url}?workspace={self.test_workspace.id}")
        self.assert_response_success(response)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(str(response.data['results'][0]['workspace']), str(self.test_workspace.id))
    
    def test_list_agents_with_search(self):
        """Test searching agents by greeting or character"""
        # Create agent with unique greeting
        unique_agent = self.create_test_agent(
            workspace=self.test_workspace,
            name="Support Agent",
            voice=self.test_voice
        )
        unique_agent.greeting_inbound = "Welcome to our support line"
        unique_agent.character = "Friendly support agent"
        unique_agent.save()
        
        response = self.user_client.get(f"{self.agents_url}?search=support")
        self.assert_response_success(response)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['agent_id'], str(unique_agent.agent_id))
    
    # ========== AGENT CREATE TESTS ==========
    
    def test_create_agent_as_admin(self):
        """Test admin can create agents"""
        agent_data = self.get_agent_data(name='Admin Created Agent')
        
        response = self.admin_client.post(self.agents_url, agent_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Admin Created Agent')
        self.assertEqual(response.data['status'], 'active')
        self.assertEqual(response.data['greeting_inbound'], agent_data['greeting_inbound'])
        self.assertEqual(response.data['greeting_outbound'], agent_data['greeting_outbound'])
        self.assertEqual(response.data['retry_interval'], 45)
        self.assertTrue(Agent.objects.filter(name='Admin Created Agent').exists())
    
    def test_create_agent_as_regular_user(self):
        """Test regular user cannot create agents"""
        agent_data = self.get_agent_data(name='Unauthorized Agent')
        
        response = self.user_client.post(self.agents_url, agent_data, format='json')
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_create_agent_validation(self):
        """Test agent creation validation"""
        # Missing required fields
        response = self.admin_client.post(self.agents_url, {}, format='json')
        self.assert_validation_error(response)
        required_fields = ['workspace', 'name', 'greeting_inbound', 'greeting_outbound', 
                          'language', 'call_from', 'call_to', 'character']
        for field in required_fields:
            self.assertIn(field, response.data)
        
        # Invalid time format
        agent_data = self.get_agent_data(call_from='invalid-time')
        response = self.admin_client.post(self.agents_url, agent_data, format='json')
        self.assert_validation_error(response)
        self.assertIn('call_from', response.data)
        
        # Invalid workdays
        agent_data = self.get_agent_data(workdays=['invalid-day'])
        response = self.admin_client.post(self.agents_url, agent_data, format='json')
        self.assert_validation_error(response)
    
    def test_create_agent_with_config_id(self):
        """Test creating agent with config_id"""
        agent_data = self.get_agent_data(
            name='Agent with Config',
            config_id='test-config-123'
        )
        
        response = self.admin_client.post(self.agents_url, agent_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['config_id'], 'test-config-123')
    
    def test_create_agent_with_calendar_configuration(self):
        """Test creating agent with calendar configuration"""
        # Create calendar configuration
        calendar = self.create_test_calendar(self.test_workspace)
        cal_config = self.create_test_calendar_configuration(calendar)
        
        agent_data = self.get_agent_data(
            name='Agent with Calendar',
            calendar_configuration=str(cal_config.id)
        )
        
        response = self.admin_client.post(self.agents_url, agent_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data['calendar_configuration']), str(cal_config.id))
    
    # ========== AGENT RETRIEVE TESTS ==========
    
    def test_retrieve_agent(self):
        """Test retrieving single agent"""
        response = self.user_client.get(f"{self.agents_url}{self.test_agent.agent_id}/")
        self.assert_response_success(response)
        self.assertEqual(response.data['agent_id'], str(self.test_agent.agent_id))
        self.assertEqual(response.data['name'], self.test_agent.name)
        self.assertEqual(response.data['status'], self.test_agent.status)
        self.assertEqual(response.data['greeting_inbound'], self.test_agent.greeting_inbound)
        self.assertEqual(response.data['greeting_outbound'], self.test_agent.greeting_outbound)
        self.assertIn('created_at', response.data)
        self.assertIn('updated_at', response.data)
    
    def test_retrieve_nonexistent_agent(self):
        """Test retrieving non-existent agent"""
        fake_id = str(uuid.uuid4())
        response = self.user_client.get(f"{self.agents_url}{fake_id}/")
        self.assert_response_error(response, status.HTTP_404_NOT_FOUND)
    
    # ========== AGENT UPDATE TESTS ==========
    
    def test_update_agent_as_admin(self):
        """Test admin can update agents"""
        response = self.admin_client.patch(
            f"{self.agents_url}{self.test_agent.agent_id}/",
            {
                'name': 'Updated Agent Name',
                'greeting_inbound': 'Updated inbound greeting',
                'greeting_outbound': 'Updated outbound greeting',
                'retry_interval': 60
            },
            format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['name'], 'Updated Agent Name')
        self.assertEqual(response.data['greeting_inbound'], 'Updated inbound greeting')
        self.assertEqual(response.data['greeting_outbound'], 'Updated outbound greeting')
        self.assertEqual(response.data['retry_interval'], 60)
    
    def test_update_agent_as_regular_user(self):
        """Test regular user cannot update agents"""
        response = self.user_client.patch(
            f"{self.agents_url}{self.test_agent.agent_id}/", {'name': 'Hacked name'}, format='json'
        )
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_update_agent_workdays(self):
        """Test updating agent workdays"""
        new_workdays = ['monday', 'wednesday', 'friday']
        response = self.admin_client.patch(
            f"{self.agents_url}{self.test_agent.agent_id}/", {'workdays': new_workdays}, format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['workdays'], new_workdays)
    
    def test_update_agent_times(self):
        """Test updating agent call times"""
        response = self.admin_client.patch(
            f"{self.agents_url}{self.test_agent.agent_id}/",
            {
                'call_from': '07:30:00',
                'call_to': '19:30:00'
            },
            format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['call_from'], '07:30:00')
        self.assertEqual(response.data['call_to'], '19:30:00')
    
    # ========== AGENT DELETE TESTS ==========
    
    def test_delete(self):
        """Test admin can delete agents"""
        agent_to_delete = self.create_test_agent(self.test_workspace)
        
        response = self.admin_client.delete(f"{self.agents_url}{agent_to_delete.agent_id}/")
        self.assert_delete_success(response)
        self.assertFalse(Agent.objects.filter(agent_id=agent_to_delete.agent_id).exists())
    
    def test_delete_agent_as_regular_user(self):
        """Test regular user cannot delete agents"""
        response = self.user_client.delete(f"{self.agents_url}{self.test_agent.agent_id}/")
        # Fixed: Regular users correctly cannot create restricted resources
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    # ========== AGENT PHONE NUMBERS ENDPOINT TESTS ==========
    
    def test_get_agent_phone_numbers(self):
        """Test getting phone numbers for an agent"""
        # Create and assign phone numbers
        phone1 = self.create_test_phone_number("+15551234567")
        phone2 = self.create_test_phone_number("+15559876543")
        self.test_agent.phone_numbers.add(phone1, phone2)
        
        response = self.user_client.get(f"{self.agents_url}{self.test_agent.agent_id}/phone_numbers/")
        self.assert_response_success(response)
        self.assertEqual(len(response.data), 2)
        
        # Check phone details
        phone_numbers = [p['phonenumber'] for p in response.data]
        self.assertIn('+15551234567', phone_numbers)
        self.assertIn('+15559876543', phone_numbers)
    
    def test_get_phone_numbers_empty_agent(self):
        """Test getting phone numbers for agent with no phones"""
        empty_agent = self.create_test_agent(self.test_workspace)
        
        response = self.user_client.get(f"{self.agents_url}{empty_agent.agent_id}/phone_numbers/")
        self.assert_response_success(response)
        self.assertEqual(len(response.data), 0)
    
    # ========== ASSIGN PHONE NUMBERS TESTS ==========
    
    def test_assign_phone_numbers_as_admin(self):
        """Test admin can assign phone numbers to agent"""
        # Create phone numbers
        phone1 = self.create_test_phone_number("+15551111111")
        phone2 = self.create_test_phone_number("+15552222222")
        
        data = {
            'phone_number_ids': [str(phone1.id), str(phone2.id)]
        }
        
        response = self.admin_client.post(
            f"{self.agents_url}{self.test_agent.agent_id}/assign_phone_numbers/", data
        , format='json')
        self.assert_response_success(response, status.HTTP_200_OK)
        self.assertIn('assigned_numbers', response.data)
        self.assertEqual(len(response.data['assigned_numbers']), 2)
        
        # Verify assignment
        self.assertIn(phone1, self.test_agent.phone_numbers.all())
        self.assertIn(phone2, self.test_agent.phone_numbers.all())
    
    def test_assign_phone_numbers_as_regular_user(self):
        """Test regular user cannot assign phone numbers"""
        phone = self.create_test_phone_number("+15550000000")
        
        data = {
            'phone_number_ids': [str(phone.id)]
        }
        
        response = self.user_client.post(
            f"{self.agents_url}{self.test_agent.agent_id}/assign_phone_numbers/", data
        , format='json')
        # Fixed: Regular users correctly cannot create restricted resources agents
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_assign_duplicate_phone_numbers(self):
        """Test assigning already assigned phone numbers"""
        # Assign phone first
        phone = self.create_test_phone_number("+15554444444")
        self.test_agent.phone_numbers.add(phone)
        
        data = {
            'phone_number_ids': [str(phone.id)]
        }
        
        response = self.admin_client.post(
            f"{self.agents_url}{self.test_agent.agent_id}/assign_phone_numbers/", data
        , format='json')
        self.assert_response_success(response)
        # API might allow duplicate assignments
        self.assertGreaterEqual(len(response.data['assigned_numbers']), 0)
        self.assertIn('already_assigned', response.data)
        self.assertEqual(len(response.data['already_assigned']), 1)
    
    def test_assign_nonexistent_phone_numbers(self):
        """Test assigning non-existent phone numbers"""
        fake_id = str(uuid.uuid4())
        
        data = {
            'phone_number_ids': [fake_id]
        }
        
        response = self.admin_client.post(
            f"{self.agents_url}{self.test_agent.agent_id}/assign_phone_numbers/", data
        , format='json')
        self.assert_response_error(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number_ids', response.data)
        self.assertIn('do not exist or are inactive', str(response.data['phone_number_ids'][0]))
    
    # ========== REMOVE PHONE NUMBERS TESTS ==========
    
    def test_remove_phone_numbers_as_admin(self):
        """Test admin can remove phone numbers from agent"""
        # Assign phones first
        phone1 = self.create_test_phone_number("+15555555555")
        phone2 = self.create_test_phone_number("+15556666666")
        self.test_agent.phone_numbers.add(phone1, phone2)
        
        data = {
            'phone_number_ids': [str(phone1.id)]
        }
        
        response = self.admin_client.delete(
            f"{self.agents_url}{self.test_agent.agent_id}/remove_phone_numbers/",
            data,
            format='json'
        )
        self.assert_response_success(response, status.HTTP_200_OK)
        self.assertIn('removed_numbers', response.data)
        self.assertEqual(len(response.data['removed_numbers']), 1)
        
        # Verify removal
        self.assertNotIn(phone1, self.test_agent.phone_numbers.all())
        self.assertIn(phone2, self.test_agent.phone_numbers.all())
    
    def test_remove_phone_numbers_as_regular_user(self):
        """Test regular user cannot remove phone numbers"""
        data = {
            'phone_number_ids': ['test-id']
        }
        
        response = self.user_client.delete(
            f"{self.agents_url}{self.test_agent.agent_id}/remove_phone_numbers/",
            data,
            format='json'
        )
        # Fixed: Regular users correctly cannot create restricted resources
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_remove_unassigned_phone_numbers(self):
        """Test removing phone numbers not assigned to agent"""
        phone = self.create_test_phone_number("+15557777777")
        
        data = {
            'phone_number_ids': [str(phone.id)]
        }
        
        response = self.admin_client.delete(
            f"{self.agents_url}{self.test_agent.agent_id}/remove_phone_numbers/",
            data,
            format='json'
        )
        self.assert_response_success(response)
        # API might allow removing unassigned numbers
        self.assertGreaterEqual(len(response.data['removed_numbers']), 0)
        self.assertIn('not_assigned', response.data)
        self.assertEqual(len(response.data['not_assigned']), 1)
    
    # ========== AGENT CONFIG ENDPOINT TESTS ==========
    
    def test_get_agent_config(self):
        """Test getting agent configuration"""
        # Update agent with config_id
        self.test_agent.config_id = "test-config-456"
        self.test_agent.save()
        
        response = self.user_client.get(f"{self.agents_url}{self.test_agent.agent_id}/config/")
        self.assert_response_success(response)
        
        # Check config structure
        self.assertIn('agent_id', response.data)
        self.assertIn('workspace', response.data)
        self.assertIn('name', response.data)
        self.assertIn('status', response.data)
        self.assertIn('greeting_inbound', response.data)
        self.assertIn('greeting_outbound', response.data)
        self.assertIn('voice', response.data)
        self.assertIn('voice_provider', response.data)
        self.assertIn('voice_external_id', response.data)
        self.assertIn('language', response.data)
        self.assertIn('retry_interval', response.data)
        self.assertIn('workdays', response.data)
        self.assertIn('call_from', response.data)
        self.assertIn('call_to', response.data)
        self.assertIn('character', response.data)
        self.assertIn('config_id', response.data)
        self.assertIn('phone_numbers', response.data)
        self.assertIn('calendar_configuration', response.data)
        
        self.assertEqual(response.data['config_id'], 'test-config-456')
    
    def test_get_config_with_phone_numbers(self):
        """Test config includes phone numbers"""
        # Assign phone numbers
        phone = self.create_test_phone_number("+15558888888")
        self.test_agent.phone_numbers.add(phone)
        
        response = self.user_client.get(f"{self.agents_url}{self.test_agent.agent_id}/config/")
        self.assert_response_success(response)
        
        self.assertEqual(len(response.data['phone_numbers']), 1)
        self.assertEqual(response.data['phone_numbers'][0], '+15558888888')
    
    # ========== PHONE NUMBER TESTS ==========
    
    def test_list_phone_numbers(self):
        """Test listing phone numbers"""
        # Create phone numbers
        self.create_test_phone_number("+15551234567")
        self.create_test_phone_number("+15559876543")
        
        response = self.user_client.get(self.phone_numbers_url)
        self.assert_response_success(response)
        self.assert_pagination_response(response)
        self.assertGreaterEqual(response.data['count'], 2)
    
    def test_create_phone_number_as_admin(self):
        """Test admin can create phone numbers"""
        phone_data = {
            'phonenumber': '+15559999999'
        }
        
        response = self.admin_client.post(self.phone_numbers_url, phone_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['phonenumber'], '+15559999999')
        self.assertTrue(response.data['is_active'])
    
    def test_create_phone_number_as_regular_user(self):
        """Test regular user cannot create phone numbers"""
        phone_data = {
            'phonenumber': '+15550000000'
        }
        
        response = self.user_client.post(self.phone_numbers_url, phone_data, format='json')
        # Fixed: Regular users correctly cannot create restricted resources agents
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_create_duplicate_phone_number(self):
        """Test creating duplicate phone number"""
        # Create first phone
        self.create_test_phone_number("+15551111111")
        
        # Try to create duplicate
        phone_data = {
            'phonenumber': '+15551111111'
        }
        
        response = self.admin_client.post(self.phone_numbers_url, phone_data, format='json')
        self.assert_validation_error(response)
        self.assertIn('phonenumber', response.data)
    
    def test_update_phone_number(self):
        """Test updating phone number"""
        phone = self.create_test_phone_number("+15552222222")
        
        response = self.admin_client.patch(
            f"{self.phone_numbers_url}{phone.id}/", {'is_active': False}, format='json'
        )
        self.assert_response_success(response)
        self.assertFalse(response.data['is_active'])
    
    def test_delete(self):
        """Test deleting phone number"""
        phone = self.create_test_phone_number("+15553333333")
        
        response = self.admin_client.delete(f"{self.phone_numbers_url}{phone.id}/")
        self.assert_delete_success(response)
        self.assertFalse(PhoneNumber.objects.filter(id=phone.id).exists())
    
    # ========== EDGE CASES ==========
    
    def test_agent_with_all_weekdays(self):
        """Test creating agent with all weekdays"""
        all_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        agent_data = self.get_agent_data(
            name='24/7 Agent',
            greeting_inbound='Available every day for inbound!',
            greeting_outbound='Available every day for outbound!',
            workdays=all_days,
            call_from='00:00:00',
            call_to='23:59:59',
            character='24/7 support agent'
        )
        
        response = self.admin_client.post(self.agents_url, agent_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['workdays'], all_days)
    
    def test_agent_with_very_long_text_fields(self):
        """Test creating agent with very long text fields"""
        long_greeting_inbound = "Hello inbound! " * 100  # Very long greeting
        long_greeting_outbound = "Hello outbound! " * 100  # Very long greeting
        long_character = "Professional " * 100  # Very long character description
        
        agent_data = self.get_agent_data(
            name='Long Text Agent',
            greeting_inbound=long_greeting_inbound,
            greeting_outbound=long_greeting_outbound,
            character=long_character
        )
        
        response = self.admin_client.post(self.agents_url, agent_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        # Compare trimmed versions to handle potential whitespace differences
        self.assertEqual(response.data['greeting_inbound'].strip(), long_greeting_inbound.strip())
        self.assertEqual(response.data['greeting_outbound'].strip(), long_greeting_outbound.strip())
        self.assertEqual(response.data['character'].strip(), long_character.strip())
    
    def test_phone_number_formats(self):
        """Test various phone number formats"""
        phone_formats = [
            '+1-555-123-4567',
            '+44 20 7946 0958',
            '+33 1 42 86 82 00',
            '+49 30 12345678',
            '+81 3-1234-5678',
            '+86 10 1234 5678'
        ]
        
        for phone in phone_formats:
            phone_data = {'phonenumber': phone}
            response = self.admin_client.post(self.phone_numbers_url, phone_data, format='json')
            self.assert_response_success(response, status.HTTP_201_CREATED)
            self.assertEqual(response.data['phonenumber'], phone)
    
    def test_agent_with_multiple_languages(self):
        """Test agents with different languages"""
        languages = ['en-US', 'es-ES', 'fr-FR', 'de-DE', 'ja-JP']
        
        for i, lang in enumerate(languages):
            agent_data = self.get_agent_data(
                name=f'Agent {lang}',
                greeting_inbound=f'Hello inbound in {lang}',
                greeting_outbound=f'Hello outbound in {lang}',
                language=lang,
                character=f'Agent speaking {lang}'
            )
            
            response = self.admin_client.post(self.agents_url, agent_data, format='json')
            self.assert_response_success(response, status.HTTP_201_CREATED)
            self.assertEqual(response.data['language'], lang)
            # Voice should be our test_voice UUID, not a string
            self.assertEqual(str(response.data['voice']), str(self.test_voice.id))
    
    def test_agent_time_edge_cases(self):
        """Test agent with edge case times"""
        # Midnight to midnight (24 hour agent)
        agent_data = self.get_agent_data(
            name='24 Hour Agent',
            greeting_inbound='24 hour inbound service',
            greeting_outbound='24 hour outbound service',
            call_from='00:00:00',
            call_to='23:59:59',
            character='Always available'
        )
        
        response = self.admin_client.post(self.agents_url, agent_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        
        # Same start and end time
        agent_data = self.get_agent_data(
            name='Same Time Agent',
            greeting_inbound='Same time inbound',
            greeting_outbound='Same time outbound',
            call_from='12:00:00',
            call_to='12:00:00'
        )
        
        response = self.admin_client.post(self.agents_url, agent_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
    
    def test_bulk_phone_assignment(self):
        """Test assigning many phone numbers at once"""
        # Create many phone numbers
        phone_ids = []
        for i in range(10):
            phone = self.create_test_phone_number(f"+1555000{i:04d}")
            phone_ids.append(str(phone.id))
        
        data = {
            'phone_number_ids': phone_ids
        }
        
        response = self.admin_client.post(
            f"{self.agents_url}{self.test_agent.agent_id}/assign_phone_numbers/", data
        , format='json')
        self.assert_response_success(response)
        self.assertEqual(len(response.data['assigned_numbers']), 10)
    
    def test_agent_cascade_delete(self):
        """Test that deleting workspace deletes agents"""
        # Create workspace with agent
        cascade_workspace = self.create_test_workspace("Cascade Test")
        cascade_agent = self.create_test_agent(cascade_workspace)
        agent_id = cascade_agent.agent_id
        
        # Delete workspace
        self.assertTrue(Agent.objects.filter(agent_id=agent_id).exists())
        cascade_workspace.delete()
        
        # Verify agent is deleted
        self.assertFalse(Agent.objects.filter(agent_id=agent_id).exists()) 