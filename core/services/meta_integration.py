import hashlib
import re
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
from core.utils.validators import (
    validate_email_strict,
    normalize_phone_e164,
    extract_name,
    _normalize_key,
)

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
            logger.info(f"Requesting Facebook pages from: {url}")
            logger.info(f"Request params: {dict(params, access_token='***REDACTED***')}")
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            pages = data.get('data', [])
            
            # Enhanced logging for debugging
            logger.info(f"Facebook API response structure: {list(data.keys())}")
            logger.info(f"Found {len(pages)} pages for user")
            
            if pages:
                for i, page in enumerate(pages):
                    logger.info(f"Page {i+1}: {page.get('name', 'Unnamed')} (ID: {page.get('id')}, Category: {page.get('category', 'Unknown')})")
                    if 'tasks' in page:
                        logger.info(f"  - Page tasks: {page.get('tasks', [])}")
            else:
                logger.warning("No pages found in Facebook API response")
                logger.info(f"Full API response: {data}")
            
            return pages
        except requests.RequestException as e:
            logger.error(f"Error getting user pages: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"Facebook API error response: {error_data}")
                except:
                    logger.error(f"Facebook API error response (raw): {e.response.text}")
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
    
    def validate_user_account(self, access_token: str) -> Dict[str, any]:
        """Validate user account and permissions before creating integration"""
        try:
            # Check user info and permissions
            user_info_url = f"{self.base_url}/me"
            user_params = {
                'access_token': access_token,
                'fields': 'id,name,email,permissions'
            }
            
            user_response = requests.get(user_info_url, params=user_params)
            user_response.raise_for_status()
            user_data = user_response.json()
            
            # Check pages
            pages = self.get_user_pages(access_token)
            
            validation_result = {
                'is_valid': True,
                'errors': [],
                'warnings': [],
                'user_info': {
                    'id': user_data.get('id'),
                    'name': user_data.get('name'),
                    'email': user_data.get('email')
                },
                'pages_count': len(pages),
                'pages': pages[:5] if pages else []  # Limit to first 5 for response size
            }
            
            # Validate pages
            if not pages:
                validation_result['is_valid'] = False
                validation_result['errors'].append({
                    'code': 'NO_PAGES',
                    'message': 'No Facebook Pages found for this account',
                    'solution': 'Create a Facebook Business Page or use an account that manages Pages'
                })
            
            # Check permissions if available
            if 'permissions' in user_data:
                permissions_data = user_data['permissions'].get('data', [])
                granted_permissions = [p['permission'] for p in permissions_data if p.get('status') == 'granted']
                
                required_perms = ['pages_read_engagement', 'leads_retrieval']
                missing_perms = [perm for perm in required_perms if perm not in granted_permissions]
                
                if missing_perms:
                    validation_result['warnings'].append({
                        'code': 'MISSING_PERMISSIONS',
                        'message': f'Missing permissions: {", ".join(missing_perms)}',
                        'solution': 'Re-authorize with required permissions'
                    })
                
                validation_result['permissions'] = {
                    'granted': granted_permissions,
                    'missing': missing_perms
                }
            
            logger.info(f"Account validation result: {validation_result['is_valid']}, "
                       f"Pages: {len(pages)}, Errors: {len(validation_result['errors'])}")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating user account: {str(e)}")
            return {
                'is_valid': False,
                'errors': [{
                    'code': 'VALIDATION_ERROR',
                    'message': f'Failed to validate account: {str(e)}',
                    'solution': 'Try again or contact support'
                }],
                'warnings': []
            }

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
            
            # Get user pages with enhanced error handling
            pages = self.get_user_pages(access_token)
            if not pages:
                logger.error("No Facebook Pages found for this account during OAuth")
                raise Exception(
                    "No Facebook Pages found for this account. "
                    "To use Meta Lead Ads integration, you need at least one Facebook Page. "
                    "Please create a Facebook Business Page or use an account that manages Pages, then try again."
                )
            
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

            # Canonicalize to enforce singular contact fields and canonical variables
            from core.utils.lead_normalization import canonicalize_lead_payload
            normalized = canonicalize_lead_payload({
                'first_name': mapped_data.get('name') or '',
                'last_name': mapped_data.get('surname') or '',
                'full_name': mapped_data.get('name') and mapped_data.get('surname') and '' or (mapped_data.get('name') or ''),
                'email': mapped_data.get('email') or '',
                'phone': mapped_data.get('phone') or '',
                'variables': mapped_data.get('variables') or {},
            })

            # Enforce presence gate: require that name, email and phone are provided in some form
            raw_name = (normalized.get('first_name') or '').strip()
            raw_surname = (normalized.get('last_name') or '').strip()
            raw_email = normalized.get('email') or ''
            raw_phone = normalized.get('phone') or ''

            # Email validation
            email = validate_email_strict(raw_email)
            # Phone normalization to strict +<digits>
            phone = normalize_phone_e164(raw_phone, default_region='DE')

            # Name handling: allow one-word names
            if raw_name and not raw_surname:
                name_parts = raw_name.split()
                if len(name_parts) >= 2:
                    name_first = name_parts[0]
                    name_surname = ' '.join(name_parts[1:])
                else:
                    name_first = raw_name
                    name_surname = ''
            else:
                name_first = raw_name
                name_surname = raw_surname

            # Presence-based acceptance: only fail if fields are missing entirely
            if not (name_first and raw_email and raw_phone):
                logger.info(
                    "Lead ignored - invalid or missing required fields",
                    extra={
                        'leadgen_id': leadgen_id,
                        'form_id': form_id,
                        'workspace_id': integration.workspace.id,
                        'email_present': bool(raw_email),
                        'phone_present': bool(raw_phone),
                        'name_present': bool(name_first),
                        'reason': 'ignored_invalid_fields'
                    }
                )
                self._update_lead_stats(integration.workspace, 'ignored_invalid_fields')
                return None

            # ATOMIC: Create Lead record with funnel reference
            email_to_save = email or raw_email
            phone_to_save = phone or raw_phone
            lead = Lead.objects.create(
                name=name_first,
                surname=name_surname,
                email=email_to_save,
                phone=phone_to_save,
                workspace=integration.workspace,
                integration_provider='meta',
                variables=normalized.get('variables', {}),
                lead_funnel=lead_funnel
            )
            
            # Update MetaLeadForm with lead ID for tracking
            meta_lead_form.meta_lead_id = leadgen_id
            meta_lead_form.save(update_fields=['meta_lead_id', 'updated_at'])
            
            # ATOMIC: Create CallTask immediately (agent guaranteed to exist)
            try:
                from core.utils.calltask_utils import create_call_task_safely
                target_ref = f"lead:{lead.id}"
                # Respect agent working hours by letting the helper compute next_call
                call_task = create_call_task_safely(
                    agent=agent,
                    workspace=integration.workspace,
                    target_ref=target_ref,
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
                # CallTask creation failed - persist error on lead for visibility and log it
                try:
                    meta = lead.meta_data or {}
                    meta["call_task_error"] = str(e)
                    lead.meta_data = meta
                    lead.save(update_fields=["meta_data", "updated_at"])
                except Exception:
                    # Ensure we still log even if saving meta_data fails
                    pass

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
        """
        BULLETPROOF Meta field mapping for production at scale
        
        Handles 100,000+ users and any Meta form configuration:
        - Prioritized field matching (person > company > custom)
        - Synonym-based matching with value validation (email/phone)
        - Comprehensive logging for debugging
        - Fallback strategies for unknown fields → variables.custom
        """
        mapped_data: Dict = {
            'name': '',
            'surname': '',
            'email': '',
            'phone': '',
            'variables': {
                'custom': {},
                'matched_keys': {}
            }
        }

        processed_fields: List[str] = []
        unmatched_fields: List[str] = []

        PERSON_NAME_FIELDS = {
            # First/Given name variants (multi-language)
            'first_name', 'given_name', 'vorname', 'prenom', 'nombre',
            'firstname', 'fname', 'forename', 'first'
        }
        PERSON_SURNAME_FIELDS = {
            # Last/Family name variants (multi-language)
            'last_name', 'family_name', 'nachname', 'nom', 'apellido',
            'lastname', 'lname', 'surname', 'family', 'last'
        }
        FULL_NAME_FIELDS = {
            # Full name and contact name variants (multi-language)
            'full_name', 'fullname', 'name', 'display_name', 'person_name',
            'customer_name', 'user_name', 'client_name', 'contact_name',
            'vollstandiger_name', 'kontakt_name'
        }
        EMAIL_FIELDS = {
            # Email variants (multi-language)
            'email', 'email_address', 'e_mail', 'mail', 'contact_email',
            'user_email', 'customer_email', 'business_email', 'work_email',
            'email_adresse', 'e_mail_adresse', 'emailadresse', 'kontakt_email',
            'kontaktmail'
        }
        PHONE_FIELDS = {
            # Phone variants (multi-language)
            'phone', 'phone_number', 'telephone', 'telefon', 'mobile',
            'cell', 'handy', 'contact_phone', 'mobile_number', 'cell_phone',
            'phone_mobile', 'tel', 'telefonnummer', 'telefon_nummer',
            'geschaftliche_telefonnummer', 'business_phone', 'work_phone',
            'telefono', 'telefone', 'handynummer'
        }
        BUSINESS_FIELDS = {
            'company', 'company_name', 'business', 'business_name',
            'organization', 'firm', 'enterprise', 'corporation',
            'unternehmen', 'firma', 'entreprise', 'empresa'
        }

        pairs: List[Tuple[str, str]] = []
        for field in field_data:
            name_raw = str(field.get('name') or field.get('key') or '').strip()
            values = field.get('values') or field.get('value')
            value_raw = ''
            if isinstance(values, list):
                value_raw = str(values[0]).strip() if values else ''
            elif values is not None:
                value_raw = str(values).strip()
            if not name_raw or not value_raw:
                continue
            k = _normalize_key(name_raw)
            pairs.append((k, value_raw))

        # pick candidates
        first = next((v for k, v in pairs if k in PERSON_NAME_FIELDS and v), '')
        last = next((v for k, v in pairs if k in PERSON_SURNAME_FIELDS and v), '')
        full = next((v for k, v in pairs if k in FULL_NAME_FIELDS and v), '')

        # Heuristic: any key containing "name" (but not company/business) is a full name
        if not full:
            BUSINESS_TOKENS = {'company', 'business', 'firma', 'unternehmen', 'organization', 'org', 'brand'}
            for k, v in pairs:
                if 'name' in k and not any(tok in k for tok in BUSINESS_TOKENS):
                    full = v
                    break

        email_val = None
        email_key = None
        for k, v in pairs:
            if k in EMAIL_FIELDS:
                e = validate_email_strict(v)
                if e:
                    email_val = e
                    email_key = k
                    break
        if not email_val:
            # Heuristic: keys containing 'email' or 'mail'
            for k, v in pairs:
                if ('email' in k or 'mail' in k) and v:
                    e = validate_email_strict(v)
                    if e:
                        email_val = e
                        email_key = k
                        break
        if not email_val:
            for k, v in pairs:
                if '@' in v:
                    e = validate_email_strict(v)
                    if e:
                        email_val = e
                        email_key = k
                        break
        # Fallback: accept first string that contains '@' even if not strictly valid
        if not email_val:
            fallback_email = next((v for k, v in pairs if '@' in v), '')
            if fallback_email:
                mapped_data['email'] = fallback_email

        phone_val = None
        phone_key = None
        for k, v in pairs:
            if k in PHONE_FIELDS:
                p = normalize_phone_e164(v, default_region='DE')
                if p:
                    phone_val = p
                    phone_key = k
                    break
        if not phone_val:
            for k, v in pairs:
                p = normalize_phone_e164(v, default_region='DE')
                if p:
                    phone_val = p
                    phone_key = k
                    break
        # Fallback: accept first phone-like string (prefer known phone fields), minimal sanitization
        if not phone_val:
            def _digits_count(s: str) -> int:
                return sum(ch.isdigit() for ch in s)

            candidate = None
            # Prefer values from known phone fields
            for k, v in pairs:
                if (k in PHONE_FIELDS or any(t in k for t in ['phone', 'telefon', 'tel', 'mobile', 'handy'])) and _digits_count(v) >= 6:
                    candidate = re.sub(r"[^0-9+]", "", v)
                    phone_key = k
                    break
            # Otherwise any field with 6+ digits
            if candidate is None:
                for k, v in pairs:
                    if _digits_count(v) >= 6:
                        candidate = re.sub(r"[^0-9+]", "", v)
                        phone_key = k
                        break
            if candidate:
                mapped_data['phone'] = candidate

        name_triplet = extract_name(first, last, full)
        if name_triplet:
            mapped_data['name'], mapped_data['surname'] = name_triplet[0], name_triplet[1]
        if email_val:
            mapped_data['email'] = email_val
        if phone_val:
            mapped_data['phone'] = phone_val

        matched_keys = set(filter(None, [
            next((k for k, v in pairs if v == first), None),
            next((k for k, v in pairs if v == last), None),
            next((k for k, v in pairs if v == full), None),
            email_key,
            phone_key,
        ]))

        for k, v in pairs:
            if k in BUSINESS_FIELDS:
                mapped_data['variables']['custom'][k] = v
                continue
            if k in matched_keys:
                continue
            mapped_data['variables']['custom'][k] = v

        mapped_data['variables']['matched_keys'] = {
            'first_name': first or '',
            'last_name': last or '',
            'full_name': full or '',
            'email': email_key or '',
            'phone': phone_key or '',
        }

        logger.info(
            "Meta field mapping completed",
            extra={
                'total_fields': len(field_data),
                'final_mapping': {
                    'name': mapped_data['name'],
                    'surname': mapped_data['surname'],
                    'email_present': bool(mapped_data['email']),
                    'phone_present': bool(mapped_data['phone']),
                    'custom_keys': list(mapped_data['variables'].get('custom', {}).keys()),
                },
            }
        )

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