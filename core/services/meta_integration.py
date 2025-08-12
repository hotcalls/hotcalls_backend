import hashlib
import hmac
import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from core.models import MetaIntegration, MetaLeadForm, Lead, Workspace

logger = logging.getLogger(__name__)


class MetaIntegrationService:
    """Service for Meta API integration"""
    
    def __init__(self):
        self.app_id = getattr(settings, 'META_APP_ID', None)
        self.app_secret = getattr(settings, 'META_APP_SECRET', None)
        self.redirect_uri = getattr(settings, 'META_REDIRECT_URI', None)
        self.api_version = getattr(settings, 'META_API_VERSION', 'v18.0')
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
    
    def get_oauth_url(self, workspace_id: str, state: str = None) -> str:
        """Generate Meta OAuth authorization URL"""
        scopes = [
            'pages_read_engagement',
            'pages_manage_metadata',
            'pages_manage_ads',
            'leads_retrieval',
            'business_management'
        ]
        
        params = {
            'client_id': self.app_id,
            'redirect_uri': self.redirect_uri,
            'scope': ','.join(scopes),
            'response_type': 'code',
            'state': state or workspace_id,
        }
        
        # Properly URL-encode all parameters
        query_string = urlencode(params)
        return f"https://www.facebook.com/{self.api_version}/dialog/oauth?{query_string}"
    
    def exchange_code_for_token(self, code: str) -> Dict:
        """Exchange OAuth code for access token"""
        url = f"{self.base_url}/oauth/access_token"
        params = {
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'redirect_uri': self.redirect_uri,
            'code': code,
        }
        
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error exchanging code for token: {str(e)}")
            raise Exception(f"Failed to exchange code for token: {str(e)}")
    
    def get_long_lived_token(self, short_token: str) -> Dict:
        """Exchange short-lived token for long-lived token"""
        url = f"{self.base_url}/oauth/access_token"
        params = {
            'grant_type': 'fb_exchange_token',
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'fb_exchange_token': short_token,
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error getting long-lived token: {str(e)}")
            raise Exception(f"Failed to get long-lived token: {str(e)}")
    
    def get_user_pages(self, access_token: str) -> List[Dict]:
        """Get user's Facebook pages"""
        url = f"{self.base_url}/me/accounts"
        params = {
            'access_token': access_token,
            'fields': 'id,name,access_token,category,tasks'
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('data', [])
        except requests.RequestException as e:
            logger.error(f"Error getting user pages: {str(e)}")
            raise Exception(f"Failed to get user pages: {str(e)}")
    
    def get_page_details(self, page_id: str, access_token: str) -> Dict:
        """Get detailed page information including name and picture"""
        url = f"{self.base_url}/{page_id}"
        params = {
            'access_token': access_token,
            'fields': 'id,name,picture,category,about,website'
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error getting page details: {str(e)}")
            raise Exception(f"Failed to get page details: {str(e)}")
    
    def get_page_lead_forms(self, page_id: str, access_token: str) -> List[Dict]:
        """Get lead forms for a specific page"""
        url = f"{self.base_url}/{page_id}/leadgen_forms"
        params = {
            'access_token': access_token,
            'fields': 'id,name,status,leads_count,created_time,questions'
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('data', [])
        except requests.RequestException as e:
            logger.error(f"Error getting lead forms: {str(e)}")
            raise Exception(f"Failed to get lead forms: {str(e)}")
    
    def get_lead_data(self, leadgen_id: str, access_token: str) -> Dict:
        """Get detailed lead data from Meta API"""
        url = f"{self.base_url}/{leadgen_id}"
        params = {
            'access_token': access_token,
            'fields': 'id,created_time,ad_id,adset_id,campaign_id,form_id,field_data'
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error getting lead data: {str(e)}")
            raise Exception(f"Failed to get lead data: {str(e)}")
    
    def setup_webhook_subscription(self, page_id: str, access_token: str, 
                                 callback_url: str, verify_token: str) -> Dict:
        """Set up webhook subscription for lead forms"""
        url = f"{self.base_url}/{page_id}/subscribed_apps"
        params = {
            'access_token': access_token,
            'subscribed_fields': 'leadgen',
            'callback_url': callback_url,
            'verify_token': verify_token,
        }
        
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error setting up webhook: {str(e)}")
            raise Exception(f"Failed to set up webhook: {str(e)}")
    
    def verify_webhook_signature(self, payload: bytes, signature: str, 
                                verification_token: str) -> bool:
        """Verify Meta webhook signature"""
        try:
            expected_signature = hmac.new(
                verification_token.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(f"sha256={expected_signature}", signature)
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False
    
    @transaction.atomic
    def create_integration(self, workspace: Workspace, oauth_data: Dict) -> MetaIntegration:
        """Create Meta integration from OAuth data"""
        try:
            # Extract token data
            access_token = oauth_data['access_token']
            expires_in = oauth_data.get('expires_in', 3600)
            token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            # Get user pages
            pages = self.get_user_pages(access_token)
            if not pages:
                raise Exception("No pages found for this account")
            
            # For now, use the first page
            # In production, you might want to let user choose
            page = pages[0]
            page_id = page['id']
            page_access_token = page['access_token']
            
            # Get detailed page information
            page_details = self.get_page_details(page_id, page_access_token)
            page_name = page_details.get('name', f'Page {page_id}')
            page_picture_url = ''
            if 'picture' in page_details and 'data' in page_details['picture']:
                page_picture_url = page_details['picture']['data'].get('url', '')
            
            # Generate verification token
            verification_token = hashlib.sha256(
                f"{workspace.id}{page_id}{timezone.now().isoformat()}".encode()
            ).hexdigest()[:32]
            
            # Create integration
            integration = MetaIntegration.objects.create(
                workspace=workspace,
                business_account_id=self.app_id,  # Using app_id as business account for now
                page_id=page_id,
                page_name=page_name,
                page_picture_url=page_picture_url,
                access_token=page_access_token,  # Store page token instead of user token
                access_token_expires_at=token_expires_at,
                verification_token=verification_token,
                scopes=['pages_read_engagement', 'leads_retrieval'],
                status='active'
            )
            
            # Set up webhook subscription
            callback_url = f"{settings.SITE_URL}/api/integrations/meta/lead_in/"
            webhook_verify_token = getattr(settings, 'META_WEBHOOK_VERIFY_TOKEN', '')
            if not webhook_verify_token:
                logger.warning("META_WEBHOOK_VERIFY_TOKEN not configured, skipping webhook setup")
            else:
                try:
                    self.setup_webhook_subscription(
                        page_id, page_access_token, callback_url, webhook_verify_token
                    )
                except Exception as e:
                    logger.warning(f"Failed to set up webhook: {str(e)}")
                    # Don't fail the integration creation if webhook setup fails
            
            # NOTE: sync_lead_forms is now handled asynchronously via Celery task
            # triggered in the OAuth callback handler
            
            return integration
            
        except Exception as e:
            logger.error(f"Error creating integration: {str(e)}")
            raise
    
    def sync_lead_forms(self, integration: MetaIntegration) -> List[MetaLeadForm]:
        """Sync lead forms from Meta API"""
        try:
            forms_data = self.get_page_lead_forms(
                integration.page_id, 
                integration.access_token
            )
            
            synced_forms = []
            for form_data in forms_data:
                form, created = MetaLeadForm.objects.get_or_create(
                    meta_integration=integration,
                    meta_form_id=form_data['id'],
                    defaults={
                        'name': form_data.get('name', f"Form {form_data['id']}")
                    }
                )
                synced_forms.append(form)
                
                if created:
                    logger.info(f"Created new lead form: {form_data['name']}")
            
            return synced_forms
            
        except Exception as e:
            logger.error(f"Error syncing lead forms: {str(e)}")
            return []

    
    def _update_lead_stats(self, workspace, reason: str):
        """Update lead processing statistics"""
        from core.models import LeadProcessingStats
        from django.utils import timezone
        
        today = timezone.now().date()
        stats, created = LeadProcessingStats.objects.get_or_create(
            workspace=workspace,
            date=today
        )
        
        # Update counters based on reason
        stats.total_received += 1
        
        if reason == 'processed':
            stats.processed_with_agent += 1
        elif reason == 'no_funnel':
            stats.ignored_no_funnel += 1
        elif reason == 'no_agent':
            stats.ignored_no_agent += 1
        elif reason == 'agent_inactive':
            stats.ignored_inactive_agent += 1
        elif reason == 'funnel_inactive':
            stats.ignored_inactive_funnel += 1
            
        stats.save()
    
    @transaction.atomic
    def process_lead_webhook(self, webhook_data: Dict, integration: MetaIntegration) -> Optional[Lead]:
        """
        Process lead webhook and create Lead record ONLY if active agent assigned
        
        PRODUCTION-READY FLOW:
        1. Find/create MetaLeadForm
        2. Check if LeadFunnel exists and is active
        3. Check if Agent assigned and is active
        4. ONLY THEN: Create Lead + CallTask atomically
        
        Performance optimized for 1000+ users:
        - Single optimized query with select_related
        - Early returns to minimize processing
        - Atomic transactions prevent race conditions
        """
        from core.models import Lead, MetaLeadForm, LeadFunnel, CallTask, CallStatus, Agent
        from django.utils import timezone
        
        try:
            leadgen_id = webhook_data.get('leadgen_id')
            form_id = webhook_data.get('form_id')
            
            if not leadgen_id or not form_id:
                logger.warning(
                    "Missing required webhook data",
                    extra={
                        'leadgen_id': leadgen_id,
                        'form_id': form_id,
                        'integration_id': integration.id,
                        'workspace_id': integration.workspace.id
                    }
                )
                return None
            
            # PERFORMANCE OPTIMIZATION: Single query with all relations
            try:
                meta_lead_form = MetaLeadForm.objects.select_related(
                    'lead_funnel',
                    'lead_funnel__agent'
                ).get(
                    meta_integration=integration,
                    meta_form_id=form_id
                )
            except MetaLeadForm.DoesNotExist:
                # Create form but no funnel yet - ignore lead
                meta_lead_form, created = MetaLeadForm.objects.get_or_create(
                    meta_integration=integration,
                    meta_form_id=form_id
                )
                logger.info(
                    "Lead ignored - form created but no funnel",
                    extra={
                        'leadgen_id': leadgen_id,
                        'form_id': form_id,
                        'workspace_id': integration.workspace.id,
                        'reason': 'no_funnel'
                    }
                )
                self._update_lead_stats(integration.workspace, 'no_funnel')
                return None
            
            # STEP 1: Check if funnel exists
            if not hasattr(meta_lead_form, 'lead_funnel') or not meta_lead_form.lead_funnel:
                logger.info(
                    "Lead ignored - no funnel for form",
                    extra={
                        'leadgen_id': leadgen_id,
                        'form_id': form_id,
                        'workspace_id': integration.workspace.id,
                        'reason': 'no_funnel'
                    }
                )
                self._update_lead_stats(integration.workspace, 'no_funnel')
                return None
                
            lead_funnel = meta_lead_form.lead_funnel
            
            # STEP 2: Check if funnel is active
            if not lead_funnel.is_active:
                logger.info(
                    "Lead ignored - funnel inactive",
                    extra={
                        'leadgen_id': leadgen_id,
                        'form_id': form_id,
                        'funnel_id': lead_funnel.id,
                        'workspace_id': integration.workspace.id,
                        'reason': 'funnel_inactive'
                    }
                )
                self._update_lead_stats(integration.workspace, 'funnel_inactive')
                return None
            
            # STEP 3: Check if agent assigned (OneToOne relation)
            if not hasattr(lead_funnel, 'agent') or not lead_funnel.agent:
                logger.info(
                    "Lead ignored - no agent assigned to funnel",
                    extra={
                        'leadgen_id': leadgen_id,
                        'form_id': form_id,
                        'funnel_id': lead_funnel.id,
                        'workspace_id': integration.workspace.id,
                        'reason': 'no_agent'
                    }
                )
                self._update_lead_stats(integration.workspace, 'no_agent')
                return None
                
            agent = lead_funnel.agent
            
            # STEP 4: Check if agent is active
            if agent.status != 'active':
                logger.info(
                    "Lead ignored - agent not active",
                    extra={
                        'leadgen_id': leadgen_id,
                        'form_id': form_id,
                        'funnel_id': lead_funnel.id,
                        'agent_id': agent.agent_id,
                        'agent_status': agent.status,
                        'workspace_id': integration.workspace.id,
                        'reason': 'agent_inactive'
                    }
                )
                self._update_lead_stats(integration.workspace, 'agent_inactive')
                return None
            
            # ✅ ALL CHECKS PASSED - Process lead with active agent
            logger.info(
                "Processing lead with active agent",
                extra={
                    'leadgen_id': leadgen_id,
                    'form_id': form_id,
                    'funnel_id': lead_funnel.id,
                    'agent_id': agent.agent_id,
                    'workspace_id': integration.workspace.id
                }
            )
            
            # Fetch detailed lead data from Meta API
            lead_data = self.get_lead_data(leadgen_id, integration.access_token)
            field_data = lead_data.get('field_data', [])
            
            # Map fields to lead model
            mapped_data = self._map_lead_fields(field_data)
            
            # ATOMIC: Create Lead record with funnel reference
            lead = Lead.objects.create(
                name=mapped_data.get('name', 'Meta Lead'),
                surname=mapped_data.get('surname', ''),
                email=mapped_data.get('email', f'lead-{leadgen_id}@meta.local'),
                phone=mapped_data.get('phone', ''),
                workspace=integration.workspace,
                integration_provider='meta',
                variables=mapped_data.get('variables', {}),
                lead_funnel=lead_funnel
            )
            
            # Update MetaLeadForm with lead ID for tracking
            meta_lead_form.meta_lead_id = leadgen_id
            meta_lead_form.save(update_fields=['meta_lead_id', 'updated_at'])
            
            # ATOMIC: Create CallTask immediately (agent guaranteed to exist)
            try:
                from core.utils.calltask_utils import create_call_task_safely
                target_ref = f"lead:{lead.id}"
                call_task = create_call_task_safely(
                    agent=agent,
                    workspace=integration.workspace,
                    target_ref=target_ref,
                    next_call=timezone.now(),  # Schedule for immediate execution
                )
                
                logger.info(
                    "Lead processed successfully",
                    extra={
                        'lead_id': lead.id,
                        'call_task_id': call_task.id,
                        'leadgen_id': leadgen_id,
                        'form_id': form_id,
                        'funnel_id': lead_funnel.id,
                        'agent_id': agent.agent_id,
                        'workspace_id': integration.workspace.id
                    }
                )
                self._update_lead_stats(integration.workspace, 'processed')
                
            except Exception as e:
                # CallTask creation failed - log but don't fail lead creation
                logger.error(
                    "Failed to create CallTask for lead",
                    extra={
                        'lead_id': lead.id,
                        'leadgen_id': leadgen_id,
                        'agent_id': agent.agent_id,
                        'error': str(e),
                        'workspace_id': integration.workspace.id
                    }
                )
                # Lead still exists, CallTask can be created later
            
            return lead
            
        except Exception as e:
            logger.error(
                "Error processing lead webhook",
                extra={
                    'leadgen_id': leadgen_id,
                    'form_id': form_id,
                    'integration_id': integration.id,
                    'workspace_id': integration.workspace.id,
                    'error': str(e)
                }
            )
            return None
    
    def _map_lead_fields(self, field_data: List[Dict]) -> Dict:
        """Map Meta field data to lead model fields"""
        mapped_data = {
            'name': '',
            'surname': '',
            'email': '',
            'phone': '',
            'variables': {}
        }
        
        for field in field_data:
            field_name = field.get('name', '')
            field_values = field.get('values', [])
            field_value = field_values[0] if field_values else ''
            
            # Simple field mapping based on field name
            field_name_lower = field_name.lower()
            
            if 'email' in field_name_lower:
                mapped_data['email'] = field_value
            elif 'phone' in field_name_lower or 'telefon' in field_name_lower:
                mapped_data['phone'] = field_value
            elif 'first_name' in field_name_lower or 'vorname' in field_name_lower:
                mapped_data['name'] = field_value
            elif 'last_name' in field_name_lower or 'nachname' in field_name_lower:
                mapped_data['surname'] = field_value
            elif 'full_name' in field_name_lower or ('name' in field_name_lower and 'first' not in field_name_lower and 'last' not in field_name_lower):
                mapped_data['name'] = field_value
            else:
                mapped_data['variables'][field_name] = field_value
        
        return mapped_data
    
    def refresh_access_token(self, integration: MetaIntegration) -> bool:
        """Refresh access token if needed"""
        try:
            # Check if token is near expiry (within 24 hours)
            if integration.access_token_expires_at > timezone.now() + timedelta(hours=24):
                return True  # Token is still valid
            
            # Try to get a new long-lived token
            token_data = self.get_long_lived_token(integration.access_token)
            
            integration.access_token = token_data['access_token']
            integration.access_token_expires_at = timezone.now() + timedelta(
                seconds=token_data.get('expires_in', 3600)
            )
            integration.save()
            
            logger.info(f"Refreshed access token for integration {integration.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error refreshing access token: {str(e)}")
            integration.status = 'expired'
            integration.save()
            return False 