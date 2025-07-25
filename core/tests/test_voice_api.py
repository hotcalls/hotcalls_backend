import uuid
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from core.models import Voice, User
from .base import BaseAPITestCase


class VoiceAPITestCase(BaseAPITestCase):
    """Test cases for Voice API"""
    
    def setUp(self):
        """Set up test data"""
        super().setUp()
        
        # Users are already created in BaseAPITestCase setUp
        # self.regular_user, self.staff_user, self.admin_user are available
        
        # Create test voices
        self.test_voice1 = Voice.objects.create(
            voice_external_id='alloy',
            provider='openai'
        )
        self.test_voice2 = Voice.objects.create(
            voice_external_id='21m00Tcm4TlvDq8ikWAM',
            provider='elevenlabs'
        )
        self.test_voice3 = Voice.objects.create(
            voice_external_id='en-US-Standard-A',
            provider='google'
        )
        
        # Create test workspace and agent using voice
        self.test_workspace = self.create_test_workspace()
        self.test_agent = self.create_test_agent(
            workspace=self.test_workspace,
            voice=self.test_voice1
        )
    
    # Authentication Tests
    
    def test_list_voices_unauthenticated(self):
        """Test unauthenticated users cannot list voices"""
        url = reverse('voice-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_list_voices_as_regular_user(self):
        """Test regular users cannot list voices"""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse('voice-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_list_voices_as_staff(self):
        """Test staff users can list voices"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 3)
    
    # CRUD Operations
    
    def test_create_voice_as_staff(self):
        """Test staff can create new voices"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        data = {
            'voice_external_id': 'nova',
            'provider': 'openai'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['voice_external_id'], 'nova')
        self.assertEqual(response.data['provider'], 'openai')
        # Note: agent_count is not included in create response (VoiceCreateSerializer)
    
    def test_create_voice_as_regular_user(self):
        """Test regular users cannot create voices"""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse('voice-list')
        data = {
            'voice_external_id': 'nova',
            'provider': 'openai'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_retrieve_voice_as_staff(self):
        """Test staff can retrieve voice details"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-detail', kwargs={'pk': str(self.test_voice1.id)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['voice_external_id'], 'alloy')
        self.assertEqual(response.data['provider'], 'openai')
        self.assertEqual(response.data['agent_count'], 1)  # Used by test_agent
    
    def test_update_voice_as_staff(self):
        """Test staff can update voices"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-detail', kwargs={'pk': str(self.test_voice2.id)})
        data = {
            'voice_external_id': 'updated_voice_id',
            'provider': 'elevenlabs'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['voice_external_id'], 'updated_voice_id')
        
        # Verify in database
        updated_voice = Voice.objects.get(id=self.test_voice2.id)
        self.assertEqual(updated_voice.voice_external_id, 'updated_voice_id')
    
    def test_partial_update_voice_as_staff(self):
        """Test staff can partially update voices"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-detail', kwargs={'pk': str(self.test_voice3.id)})
        data = {'voice_external_id': 'en-US-Standard-B'}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['voice_external_id'], 'en-US-Standard-B')
        self.assertEqual(response.data['provider'], 'google')  # Unchanged
    
    def test_delete_voice_as_staff(self):
        """Test staff can delete unused voices"""
        self.client.force_authenticate(user=self.staff_user)
        # Use voice3 which has no agents
        url = reverse('voice-detail', kwargs={'pk': str(self.test_voice3.id)})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify deleted
        self.assertFalse(Voice.objects.filter(id=self.test_voice3.id).exists())
    
    def test_delete_voice_with_agents(self):
        """Test deleting voice that has agents (should work, sets agents.voice to NULL)"""
        self.client.force_authenticate(user=self.staff_user)
        # Use voice1 which has test_agent
        url = reverse('voice-detail', kwargs={'pk': str(self.test_voice1.id)})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify voice deleted
        self.assertFalse(Voice.objects.filter(id=self.test_voice1.id).exists())
        
        # Verify agent's voice is now None
        self.test_agent.refresh_from_db()
        self.assertIsNone(self.test_agent.voice)
    
    # Validation Tests
    
    def test_create_voice_validation_empty_external_id(self):
        """Test validation for empty voice external ID"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        data = {
            'voice_external_id': '',
            'provider': 'openai'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('voice_external_id', response.data)
    
    def test_create_voice_validation_invalid_provider(self):
        """Test validation for invalid provider"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        data = {
            'voice_external_id': 'test_voice',
            'provider': 'invalid_provider'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('provider', response.data)
    
    def test_create_voice_validation_duplicate(self):
        """Test validation for duplicate voice external ID + provider"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        data = {
            'voice_external_id': 'alloy',  # Already exists for openai
            'provider': 'openai'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Voice with external ID', str(response.data))
    
    def test_create_voice_validation_long_external_id(self):
        """Test validation for too long voice external ID"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        data = {
            'voice_external_id': 'x' * 256,  # Too long
            'provider': 'openai'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('voice_external_id', response.data)
    
    def test_update_voice_validation_duplicate(self):
        """Test validation for duplicate on update"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-detail', kwargs={'pk': str(self.test_voice2.id)})
        data = {
            'voice_external_id': 'alloy',  # Already used by test_voice1
            'provider': 'openai'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Voice with external ID', str(response.data))
    
    # Provider Validation Tests
    
    def test_valid_providers(self):
        """Test all valid providers work"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        
        valid_providers = ['openai', 'elevenlabs', 'google', 'azure', 'aws']
        
        for i, provider in enumerate(valid_providers):
            data = {
                'voice_external_id': f'test_voice_{i}',
                'provider': provider
            }
            response = self.client.post(url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data['provider'], provider.lower())
    
    def test_provider_case_normalization(self):
        """Test provider is normalized to lowercase"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        data = {
            'voice_external_id': 'test_voice_caps',
            'provider': 'OPENAI'  # Uppercase
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['provider'], 'openai')  # Normalized to lowercase
    
    # Filtering Tests
    
    def test_filter_by_provider(self):
        """Test filtering voices by provider"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        
        # Filter by OpenAI
        response = self.client.get(url, {'provider': 'openai'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['provider'], 'openai')
    
    def test_filter_by_voice_external_id(self):
        """Test filtering by voice external ID"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        
        response = self.client.get(url, {'voice_external_id': 'alloy'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['voice_external_id'], 'alloy')
    
    def test_filter_has_agents(self):
        """Test filtering voices by agent assignment"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        
        # Voices with agents
        response = self.client.get(url, {'has_agents': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)  # Only test_voice1 has agent
        
        # Voices without agents
        response = self.client.get(url, {'has_agents': 'false'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)  # test_voice2 and test_voice3
    
    def test_search_voices(self):
        """Test searching voices globally"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        
        # Search by voice external ID
        response = self.client.get(url, {'search': 'alloy'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        
        # Search by provider
        response = self.client.get(url, {'search': 'google'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_ordering_voices(self):
        """Test ordering voices"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-list')
        
        # Order by provider
        response = self.client.get(url, {'ordering': 'provider'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        providers = [voice['provider'] for voice in response.data['results']]
        self.assertEqual(providers, sorted(providers))
        
        # Order by voice_external_id descending
        response = self.client.get(url, {'ordering': '-voice_external_id'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        external_ids = [voice['voice_external_id'] for voice in response.data['results']]
        self.assertEqual(external_ids, sorted(external_ids, reverse=True))
    
    # Statistics Endpoint Tests
    
    def test_voice_statistics_as_staff(self):
        """Test voice statistics endpoint for staff"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-statistics')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check response structure
        self.assertIn('total_voices', response.data)
        self.assertIn('total_assigned_agents', response.data)
        self.assertIn('provider_breakdown', response.data)
        self.assertIn('most_used_voice', response.data)
        self.assertIn('unassigned_voices', response.data)
        
        # Check values
        self.assertEqual(response.data['total_voices'], 3)
        self.assertEqual(response.data['total_assigned_agents'], 1)
        self.assertEqual(response.data['unassigned_voices'], 2)
        
        # Check most used voice
        most_used = response.data['most_used_voice']
        self.assertEqual(most_used['voice_external_id'], 'alloy')
        self.assertEqual(most_used['provider'], 'openai')
        self.assertEqual(most_used['agent_count'], 1)
    
    def test_voice_statistics_as_regular_user(self):
        """Test regular user cannot access statistics"""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse('voice-statistics')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    # Error Handling Tests
    
    def test_retrieve_nonexistent_voice(self):
        """Test retrieving non-existent voice"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-detail', kwargs={'pk': str(uuid.uuid4())})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_update_nonexistent_voice(self):
        """Test updating non-existent voice"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-detail', kwargs={'pk': str(uuid.uuid4())})
        data = {'voice_external_id': 'nonexistent'}
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_delete_nonexistent_voice(self):
        """Test deleting non-existent voice"""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse('voice-detail', kwargs={'pk': str(uuid.uuid4())})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    # Agent Count Tests
    
    def test_agent_count_in_response(self):
        """Test agent_count field is correctly calculated"""
        self.client.force_authenticate(user=self.staff_user)
        
        # Create another agent using the same voice
        agent2 = self.create_test_agent(
            workspace=self.test_workspace,
            voice=self.test_voice1,
            name="Agent 2"
        )
        
        url = reverse('voice-detail', kwargs={'pk': str(self.test_voice1.id)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['agent_count'], 2)  # Now 2 agents use this voice 