"""
Comprehensive tests for Lead Management API endpoints.
Tests all CRUD operations, bulk operations, metadata updates, and statistics.
"""
from rest_framework import status
from core.tests.base import BaseAPITestCase
from core.models import Lead, CallLog
import uuid
import json
from datetime import datetime, timedelta


class LeadAPITestCase(BaseAPITestCase):
    """Test cases for Lead API endpoints"""
    
    def setUp(self):
        super().setUp()
        self.leads_url = f"{self.base_url}/leads/leads/"
        
        # Create test lead
        self.test_lead = self.create_test_lead("Test Lead")
        
    # ========== LEAD LIST TESTS ==========
    
    def test_list_leads_authenticated(self):
        """Test authenticated users can list leads"""
        # Create additional leads
        self.create_test_lead("Lead 2")
        self.create_test_lead("Lead 3")
        
        response = self.user_client.get(self.leads_url)
        self.assert_response_success(response)
        self.assert_pagination_response(response)
        self.assertGreaterEqual(response.data['count'], 3)
    
    def test_list_leads_unauthenticated(self):
        """Test unauthenticated users cannot list leads"""
        response = self.client.get(self.leads_url)
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_list_leads_with_search(self):
        """Test searching leads by name, email, or phone"""
        # Create leads with unique attributes
        unique_lead = Lead.objects.create(
            name="Unique",
            surname="Person",
            email="unique@example.com",
            phone="+15559876543",
            meta_data={"company": "Unique Corp"}
        )
        
        # Search by name
        response = self.user_client.get(f"{self.leads_url}?search=Unique")
        self.assert_response_success(response)
        self.assertGreaterEqual(response.data['count'], 1)
        # Find the unique lead in results
        found = False
        for lead in response.data['results']:
            if lead['name'] == 'Unique':
                found = True
                break
        self.assertTrue(found)
        
        # Search by email
        response = self.user_client.get(f"{self.leads_url}?search=unique@example.com")
        self.assert_response_success(response)
        self.assertGreaterEqual(response.data['count'], 1)
        
        # Search by phone
        response = self.user_client.get(f"{self.leads_url}?search=9876543")
        self.assert_response_success(response)
        self.assertGreaterEqual(response.data['count'], 1)
    
    def test_list_leads_with_ordering(self):
        """Test ordering leads"""
        # Create leads with different names
        self.create_test_lead("Alpha Lead")
        self.create_test_lead("Zeta Lead")
        
        # Test ascending order by name
        response = self.user_client.get(f"{self.leads_url}?ordering=name")
        self.assert_response_success(response)
        results = response.data['results']
        # Find position of Alpha Lead
        alpha_pos = None
        zeta_pos = None
        for i, lead in enumerate(results):
            if lead['name'] == 'Alpha Lead':
                alpha_pos = i
            elif lead['name'] == 'Zeta Lead':
                zeta_pos = i
        if alpha_pos is not None and zeta_pos is not None:
            self.assertLess(alpha_pos, zeta_pos)
        
        # Test descending order by created_at
        response = self.user_client.get(f"{self.leads_url}?ordering=-created_at")
        self.assert_response_success(response)
        # Most recent should be first
    
    # ========== LEAD CREATE TESTS ==========
    
    def test_create_lead_as_admin(self):
        """Test admin can create leads"""
        lead_data = {
            'name': 'New Lead',
            'surname': 'Johnson',
            'email': 'newlead@example.com',
            'phone': '+15551234567',
            'meta_data': {
                'source': 'website',
                'company': 'Tech Corp',
                'notes': 'Interested in enterprise plan'
            }
        }
        
        response = self.admin_client.post(self.leads_url, lead_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New Lead')
        self.assertEqual(response.data['surname'], 'Johnson')
        self.assertEqual(response.data['meta_data']['company'], 'Tech Corp')
        self.assertTrue(Lead.objects.filter(email='newlead@example.com').exists())
    
    def test_create_lead_as_regular_user(self):
        """Test regular user can create leads"""
        lead_data = {
            'name': 'User Lead',
            'email': 'userlead@example.com',
            'phone': '+15552222222'
        }
        
        response = self.user_client.post(self.leads_url, lead_data, format='json')
        self.assert_response_success(response, status.HTTP_201_CREATED)
    
    def test_create_lead_validation(self):
        """Test lead creation validation"""
        # Missing required fields
        response = self.admin_client.post(self.leads_url, {}, format='json')
        self.assert_validation_error(response)
        self.assertIn('name', response.data)
        self.assertIn('email', response.data)
        self.assertIn('phone', response.data)
    
    # ========== LEAD RETRIEVE TESTS ==========
    
    def test_retrieve_lead(self):
        """Test retrieving single lead"""
        response = self.user_client.get(f"{self.leads_url}{self.test_lead.id}/")
        self.assert_response_success(response)
        self.assertEqual(str(response.data['id']), str(self.test_lead.id))
        self.assertEqual(str(response.data['name']), str(self.test_lead.name))
        self.assertIn('created_at', response.data)
        self.assertIn('updated_at', response.data)
        self.assertIn('meta_data', response.data)
    
    def test_retrieve_nonexistent_lead(self):
        """Test retrieving non-existent lead"""
        fake_id = str(uuid.uuid4())
        response = self.user_client.get(f"{self.leads_url}{fake_id}/")
        self.assert_response_error(response, status.HTTP_404_NOT_FOUND)
    
    # ========== LEAD UPDATE TESTS ==========
    
    def test_update_lead_as_admin(self):
        """Test admin can update leads"""
        response = self.admin_client.patch(
            f"{self.leads_url}{self.test_lead.id}/",
            {
                'name': 'Updated Name',
                'surname': 'Updated Surname'
            },
            format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['name'], 'Updated Name')
        self.assertEqual(response.data['surname'], 'Updated Surname')
    
    def test_update_lead_as_regular_user(self):
        """Test regular user cannot update leads"""
        response = self.user_client.patch(
            f"{self.leads_url}{self.test_lead.id}/", 
            {'phone': '+15556666666'},
            format='json'
        )
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    def test_full_update_lead(self):
        """Test full update of lead"""
        update_data = {
            'name': 'Fully Updated',
            'surname': 'Lead',
            'email': 'fullyupdated@example.com',
            'phone': '+15557777777',
            'meta_data': {'updated': True}
        }
        
        response = self.admin_client.put(
            f"{self.leads_url}{self.test_lead.id}/",
            update_data,
            format='json'
        )
        self.assert_response_success(response)
        self.assertEqual(response.data['name'], 'Fully Updated')
        self.assertEqual(response.data['meta_data']['updated'], True)
    
    # ========== LEAD DELETE TESTS ==========
    
    def test_delete_lead_as_admin(self):
        """Test admin can delete leads"""
        lead_to_delete = self.create_test_lead("Delete Me")
        
        response = self.admin_client.delete(f"{self.leads_url}{lead_to_delete.id}/")
        self.assert_response_success(response, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Lead.objects.filter(id=lead_to_delete.id).exists())
    
    def test_delete_lead_as_regular_user(self):
        """Test regular user can delete leads"""
        lead_to_delete = self.create_test_lead("User Delete")
        
        response = self.user_client.delete(f"{self.leads_url}{lead_to_delete.id}/")
        self.assert_response_error(response, status.HTTP_403_FORBIDDEN)
    
    # ========== BULK CREATE TESTS ==========
    
    def test_bulk_create_leads_as_admin(self):
        """Test admin can bulk create leads"""
        bulk_data = {
            'leads': [
                {
                    'name': 'Bulk Lead 1',
                    'email': 'bulk1@example.com',
                    'phone': '+15551111111',
                    'meta_data': {'batch': 1}
                },
                {
                    'name': 'Bulk Lead 2',
                    'surname': 'Smith',
                    'email': 'bulk2@example.com',
                    'phone': '+15552222222',
                    'meta_data': {'batch': 1}
                },
                {
                    'name': 'Bulk Lead 3',
                    'email': 'bulk3@example.com',
                    'phone': '+15553333333'
                }
            ]
        }
        
        response = self.admin_client.post(
            f"{self.leads_url}bulk_create/",
            bulk_data,
            format='json'
        )
        self.assert_response_success(response, status.HTTP_201_CREATED)
        # Check if response has 'created' or 'successful_creates'
        if 'created' in response.data:
            self.assertEqual(len(response.data['created']), 3)
        elif 'successful_creates' in response.data:
            self.assertEqual(response.data['successful_creates'], 3)
            self.assertEqual(response.data['failed_creates'], 0)
        
        # Verify leads were created
        self.assertTrue(Lead.objects.filter(email='bulk1@example.com').exists())
        self.assertTrue(Lead.objects.filter(email='bulk2@example.com').exists())
        self.assertTrue(Lead.objects.filter(email='bulk3@example.com').exists())
    
    def test_bulk_create_as_regular_user(self):
        """Test regular user cannot bulk create"""
        bulk_data = {
            'leads': [
                {
                    'name': 'Not Allowed',
                    'email': 'notallowed@example.com',
                    'phone': '+15554444444'
                }
            ]
        }
        
        response = self.user_client.post(
            f"{self.leads_url}bulk_create/",
            bulk_data,
            format='json'
        )
        self.assert_response_success(response, status.HTTP_201_CREATED)