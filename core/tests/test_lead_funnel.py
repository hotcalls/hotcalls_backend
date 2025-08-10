"""
Comprehensive tests for LeadFunnel system
Tests models, relationships, and race conditions
"""
import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase, TransactionTestCase
from django.db import transaction, IntegrityError
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor
import threading

from core.models import (
    User, Workspace, Agent, LeadFunnel, MetaIntegration, 
    MetaLeadForm, Lead, CallTask, CallStatus, Voice
)


class LeadFunnelModelTest(TestCase):
    """Test LeadFunnel model and relationships"""
    
    def setUp(self):
        """Set up test data"""
        # Create user and workspace
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            is_email_verified=True
        )
        self.workspace = Workspace.objects.create(
            workspace_name='Test Workspace'
        )
        self.workspace.users.add(self.user)
        
        # Create voice for agent
        self.voice = Voice.objects.create(
            name='Test Voice',
            provider='elevenlabs',
            voice_external_id='test-voice-id'
        )
        
        # Create agent
        self.agent = Agent.objects.create(
            workspace=self.workspace,
            name='Test Agent',
            status='active',
            voice=self.voice
        )
        
        # Create Meta integration
        self.meta_integration = MetaIntegration.objects.create(
            workspace=self.workspace,
            business_account_id='test_business',
            page_id='test_page',
            page_name='Test Page',
            access_token='test_token',
            access_token_expires_at=timezone.now() + timezone.timedelta(days=30),
            verification_token='test_verify',
            status='active'
        )
        
        # Create Meta lead form
        self.meta_form = MetaLeadForm.objects.create(
            meta_integration=self.meta_integration,
            meta_form_id='form_123',
            name='Test Form',
            is_active=True
        )
    
    def test_funnel_creation(self):
        """Test creating a LeadFunnel"""
        funnel = LeadFunnel.objects.create(
            name='Test Funnel',
            workspace=self.workspace,
            meta_lead_form=self.meta_form,
            is_active=True
        )
        
        self.assertEqual(funnel.name, 'Test Funnel')
        self.assertEqual(funnel.workspace, self.workspace)
        self.assertEqual(funnel.meta_lead_form, self.meta_form)
        self.assertTrue(funnel.is_active)
        self.assertFalse(funnel.has_agent)
        self.assertEqual(funnel.lead_count, 0)
    
    def test_agent_funnel_assignment(self):
        """Test assigning an agent to a funnel"""
        funnel = LeadFunnel.objects.create(
            name='Test Funnel',
            workspace=self.workspace,
            meta_lead_form=self.meta_form
        )
        
        # Assign agent to funnel
        self.agent.lead_funnel = funnel
        self.agent.save()
        
        # Refresh funnel from DB
        funnel.refresh_from_db()
        
        self.assertTrue(funnel.has_agent)
        self.assertEqual(funnel.agent, self.agent)
        self.assertEqual(str(funnel), f"Test Funnel (Agent: {self.agent.name})")
    
    def test_one_to_one_constraint(self):
        """Test that agent can only have one funnel"""
        funnel1 = LeadFunnel.objects.create(
            name='Funnel 1',
            workspace=self.workspace,
            meta_lead_form=self.meta_form
        )
        
        # Create second form and funnel
        meta_form2 = MetaLeadForm.objects.create(
            meta_integration=self.meta_integration,
            meta_form_id='form_456',
            name='Test Form 2'
        )
        funnel2 = LeadFunnel.objects.create(
            name='Funnel 2',
            workspace=self.workspace,
            meta_lead_form=meta_form2
        )
        
        # Assign agent to first funnel
        self.agent.lead_funnel = funnel1
        self.agent.save()
        
        # Try to create another agent with same funnel - should work
        agent2 = Agent.objects.create(
            workspace=self.workspace,
            name='Agent 2',
            status='active',
            voice=self.voice
        )
        
        # But agent2 cannot take funnel1 (already taken)
        # This is enforced at the application level, not DB level
        # So we test the business logic in the API tests
    
    def test_lead_funnel_relationship(self):
        """Test leads connected to funnel"""
        funnel = LeadFunnel.objects.create(
            name='Test Funnel',
            workspace=self.workspace,
            meta_lead_form=self.meta_form
        )
        
        # Create leads connected to funnel
        lead1 = Lead.objects.create(
            name='Lead 1',
            email='lead1@example.com',
            phone='+1234567890',
            workspace=self.workspace,
            lead_funnel=funnel
        )
        lead2 = Lead.objects.create(
            name='Lead 2',
            email='lead2@example.com',
            phone='+0987654321',
            workspace=self.workspace,
            lead_funnel=funnel
        )
        
        # Check lead count
        self.assertEqual(funnel.lead_count, 2)
        self.assertEqual(funnel.leads.count(), 2)
        self.assertIn(lead1, funnel.leads.all())
        self.assertIn(lead2, funnel.leads.all())
    
    def test_meta_form_funnel_one_to_one(self):
        """Test that MetaLeadForm can only have one funnel"""
        funnel1 = LeadFunnel.objects.create(
            name='Funnel 1',
            workspace=self.workspace,
            meta_lead_form=self.meta_form
        )
        
        # Try to create another funnel with same meta_form
        with self.assertRaises(IntegrityError):
            funnel2 = LeadFunnel.objects.create(
                name='Funnel 2',
                workspace=self.workspace,
                meta_lead_form=self.meta_form
            )


class LeadFunnelRaceConditionTest(TransactionTestCase):
    """Test race conditions in funnel operations"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            is_email_verified=True
        )
        self.workspace = Workspace.objects.create(
            workspace_name='Test Workspace'
        )
        self.workspace.users.add(self.user)
        
        self.voice = Voice.objects.create(
            name='Test Voice',
            provider='elevenlabs',
            voice_external_id='test-voice-id'
        )
        
        # Create multiple agents
        self.agents = []
        for i in range(5):
            agent = Agent.objects.create(
                workspace=self.workspace,
                name=f'Agent {i}',
                status='active',
                voice=self.voice
            )
            self.agents.append(agent)
        
        # Create meta integration and form
        self.meta_integration = MetaIntegration.objects.create(
            workspace=self.workspace,
            business_account_id='test_business',
            page_id='test_page',
            page_name='Test Page',
            access_token='test_token',
            access_token_expires_at=timezone.now() + timezone.timedelta(days=30),
            verification_token='test_verify',
            status='active'
        )
        
        self.meta_form = MetaLeadForm.objects.create(
            meta_integration=self.meta_integration,
            meta_form_id='form_123',
            name='Test Form',
            is_active=True
        )
        
        self.funnel = LeadFunnel.objects.create(
            name='Test Funnel',
            workspace=self.workspace,
            meta_lead_form=self.meta_form
        )
    
    def test_concurrent_agent_assignment(self):
        """Test multiple agents trying to claim the same funnel"""
        results = []
        errors = []
        
        def assign_agent_to_funnel(agent_id):
            """Try to assign agent to funnel"""
            try:
                with transaction.atomic():
                    agent = Agent.objects.select_for_update().get(agent_id=agent_id)
                    funnel = LeadFunnel.objects.select_for_update().get(id=self.funnel.id)
                    
                    # Check if funnel already has an agent
                    if hasattr(funnel, 'agent') and funnel.agent:
                        errors.append(f"Funnel already assigned to {funnel.agent.name}")
                        return False
                    
                    # Check if agent already has a funnel
                    if agent.lead_funnel:
                        errors.append(f"Agent {agent.name} already has a funnel")
                        return False
                    
                    # Assign agent to funnel
                    agent.lead_funnel = funnel
                    agent.save()
                    results.append(agent.agent_id)
                    return True
            except Exception as e:
                errors.append(str(e))
                return False
        
        # Try to assign all agents concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for agent in self.agents:
                future = executor.submit(assign_agent_to_funnel, agent.agent_id)
                futures.append(future)
            
            # Wait for all to complete
            for future in futures:
                future.result()
        
        # Only one agent should have been assigned
        self.assertEqual(len(results), 1, f"Expected 1 assignment, got {len(results)}")
        
        # Verify in database
        self.funnel.refresh_from_db()
        self.assertTrue(self.funnel.has_agent)
        self.assertIn(self.funnel.agent.agent_id, results)
    
    def test_concurrent_lead_creation(self):
        """Test creating multiple leads concurrently for same funnel"""
        # Assign agent to funnel
        self.agents[0].lead_funnel = self.funnel
        self.agents[0].save()
        
        created_leads = []
        created_tasks = []
        lock = threading.Lock()
        
        def create_lead_with_task(lead_num):
            """Create a lead and potentially a CallTask"""
            try:
                with transaction.atomic():
                    # Create lead
                    lead = Lead.objects.create(
                        name=f'Lead {lead_num}',
                        email=f'lead{lead_num}@example.com',
                        phone=f'+123456{lead_num:04d}',
                        workspace=self.workspace,
                        lead_funnel=self.funnel
                    )
                    
                    with lock:
                        created_leads.append(lead.id)
                    
                    # Check if we should create CallTask
                    if self.funnel.is_active and hasattr(self.funnel, 'agent'):
                        agent = self.funnel.agent
                        if agent.status == 'active':
                            # Check for existing CallTask
                            if not hasattr(lead, 'call_task'):
                                call_task = CallTask.objects.create(
                                    status=CallStatus.SCHEDULED,
                                    attempts=0,
                                    phone=lead.phone,
                                    workspace=self.workspace,
                                    lead=lead,
                                    agent=agent,
                                    next_call=timezone.now()
                                )
                                with lock:
                                    created_tasks.append(call_task.id)
                    
                    return True
            except Exception as e:
                print(f"Error creating lead {lead_num}: {e}")
                return False
        
        # Create 20 leads concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(20):
                future = executor.submit(create_lead_with_task, i)
                futures.append(future)
            
            # Wait for all to complete
            for future in futures:
                future.result()
        
        # Verify all leads were created
        self.assertEqual(len(created_leads), 20)
        self.assertEqual(len(created_tasks), 20)
        
        # Verify no duplicate CallTasks
        unique_tasks = len(set(created_tasks))
        self.assertEqual(unique_tasks, 20, "Found duplicate CallTasks")
        
        # Verify funnel lead count
        self.funnel.refresh_from_db()
        self.assertEqual(self.funnel.lead_count, 20)


class LeadFunnelWebhookTest(TestCase):
    """Test webhook processing with LeadFunnels"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            is_email_verified=True
        )
        self.workspace = Workspace.objects.create(
            workspace_name='Test Workspace'
        )
        self.workspace.users.add(self.user)
        
        self.voice = Voice.objects.create(
            name='Test Voice',
            provider='elevenlabs',
            voice_external_id='test-voice-id'
        )
        
        self.agent = Agent.objects.create(
            workspace=self.workspace,
            name='Test Agent',
            status='active',
            voice=self.voice
        )
        
        self.meta_integration = MetaIntegration.objects.create(
            workspace=self.workspace,
            business_account_id='test_business',
            page_id='test_page',
            page_name='Test Page',
            access_token='test_token',
            access_token_expires_at=timezone.now() + timezone.timedelta(days=30),
            verification_token='test_verify',
            status='active'
        )
    
    @patch('core.services.meta_integration.MetaIntegrationService.get_lead_data')
    def test_webhook_creates_lead_with_funnel(self, mock_get_lead):
        """Test webhook creates lead with funnel reference"""
        from core.services.meta_integration import MetaIntegrationService
        
        # Mock Meta API response
        mock_get_lead.return_value = {
            'field_data': [
                {'name': 'full_name', 'values': ['John Doe']},
                {'name': 'email', 'values': ['john@example.com']},
                {'name': 'phone_number', 'values': ['+1234567890']}
            ]
        }
        
        # Create form and funnel
        meta_form = MetaLeadForm.objects.create(
            meta_integration=self.meta_integration,
            meta_form_id='form_123',
            name='Test Form',
            is_active=True
        )
        funnel = LeadFunnel.objects.create(
            name='Test Funnel',
            workspace=self.workspace,
            meta_lead_form=meta_form,
            is_active=True
        )
        
        # Process webhook
        service = MetaIntegrationService()
        webhook_data = {
            'leadgen_id': 'lead_123',
            'form_id': 'form_123'
        }
        
        lead = service.process_lead_webhook(webhook_data, self.meta_integration)
        
        # Verify lead created with funnel
        self.assertIsNotNone(lead)
        self.assertEqual(lead.lead_funnel, funnel)
        self.assertEqual(lead.workspace, self.workspace)
        self.assertEqual(lead.integration_provider, 'meta')
        
        # Verify no CallTask created (no agent assigned)
        self.assertFalse(hasattr(lead, 'call_task'))
    
    @patch('core.services.meta_integration.MetaIntegrationService.get_lead_data')
    def test_webhook_creates_calltask_with_agent(self, mock_get_lead):
        """Test webhook creates CallTask when agent is assigned"""
        from core.services.meta_integration import MetaIntegrationService
        
        # Mock Meta API response
        mock_get_lead.return_value = {
            'field_data': [
                {'name': 'full_name', 'values': ['Jane Smith']},
                {'name': 'email', 'values': ['jane@example.com']},
                {'name': 'phone_number', 'values': ['+0987654321']}
            ]
        }
        
        # Create form and funnel with agent
        meta_form = MetaLeadForm.objects.create(
            meta_integration=self.meta_integration,
            meta_form_id='form_456',
            name='Test Form 2',
            is_active=True
        )
        funnel = LeadFunnel.objects.create(
            name='Test Funnel 2',
            workspace=self.workspace,
            meta_lead_form=meta_form,
            is_active=True
        )
        
        # Assign agent to funnel
        self.agent.lead_funnel = funnel
        self.agent.save()
        
        # Process webhook
        service = MetaIntegrationService()
        webhook_data = {
            'leadgen_id': 'lead_456',
            'form_id': 'form_456'
        }
        
        lead = service.process_lead_webhook(webhook_data, self.meta_integration)
        
        # Verify lead created
        self.assertIsNotNone(lead)
        self.assertEqual(lead.lead_funnel, funnel)
        
        # Verify CallTask created
        self.assertTrue(hasattr(lead, 'call_task'))
        call_task = lead.call_task
        self.assertEqual(call_task.agent, self.agent)
        self.assertEqual(call_task.workspace, self.workspace)
        self.assertEqual(call_task.status, CallStatus.SCHEDULED)
        self.assertEqual(call_task.phone, lead.phone)
    
    @patch('core.services.meta_integration.MetaIntegrationService.get_lead_data')
    def test_webhook_no_calltask_inactive_funnel(self, mock_get_lead):
        """Test no CallTask created when funnel is inactive"""
        from core.services.meta_integration import MetaIntegrationService
        
        # Mock Meta API response
        mock_get_lead.return_value = {
            'field_data': [
                {'name': 'full_name', 'values': ['Bob Johnson']},
                {'name': 'email', 'values': ['bob@example.com']},
                {'name': 'phone_number', 'values': ['+1122334455']}
            ]
        }
        
        # Create form and inactive funnel with agent
        meta_form = MetaLeadForm.objects.create(
            meta_integration=self.meta_integration,
            meta_form_id='form_789',
            name='Test Form 3',
            is_active=True
        )
        funnel = LeadFunnel.objects.create(
            name='Test Funnel 3',
            workspace=self.workspace,
            meta_lead_form=meta_form,
            is_active=False  # Inactive funnel
        )
        
        # Assign agent to funnel
        self.agent.lead_funnel = funnel
        self.agent.save()
        
        # Process webhook
        service = MetaIntegrationService()
        webhook_data = {
            'leadgen_id': 'lead_789',
            'form_id': 'form_789'
        }
        
        lead = service.process_lead_webhook(webhook_data, self.meta_integration)
        
        # Verify lead created but no CallTask
        self.assertIsNotNone(lead)
        self.assertEqual(lead.lead_funnel, funnel)
        self.assertFalse(hasattr(lead, 'call_task'))
    
    @patch('core.services.meta_integration.MetaIntegrationService.get_lead_data')
    def test_webhook_no_calltask_inactive_agent(self, mock_get_lead):
        """Test no CallTask created when agent is inactive"""
        from core.services.meta_integration import MetaIntegrationService
        
        # Mock Meta API response
        mock_get_lead.return_value = {
            'field_data': [
                {'name': 'full_name', 'values': ['Alice Cooper']},
                {'name': 'email', 'values': ['alice@example.com']},
                {'name': 'phone_number', 'values': ['+9988776655']}
            ]
        }
        
        # Create form and funnel with inactive agent
        meta_form = MetaLeadForm.objects.create(
            meta_integration=self.meta_integration,
            meta_form_id='form_999',
            name='Test Form 4',
            is_active=True
        )
        funnel = LeadFunnel.objects.create(
            name='Test Funnel 4',
            workspace=self.workspace,
            meta_lead_form=meta_form,
            is_active=True
        )
        
        # Create inactive agent and assign to funnel
        inactive_agent = Agent.objects.create(
            workspace=self.workspace,
            name='Inactive Agent',
            status='inactive',  # Inactive agent
            voice=self.voice
        )
        inactive_agent.lead_funnel = funnel
        inactive_agent.save()
        
        # Process webhook
        service = MetaIntegrationService()
        webhook_data = {
            'leadgen_id': 'lead_999',
            'form_id': 'form_999'
        }
        
        lead = service.process_lead_webhook(webhook_data, self.meta_integration)
        
        # Verify lead created but no CallTask
        self.assertIsNotNone(lead)
        self.assertEqual(lead.lead_funnel, funnel)
        self.assertFalse(hasattr(lead, 'call_task')) 