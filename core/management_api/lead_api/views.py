from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample

from core.models import Lead, CallLog, Workspace, LeadFunnel
from .serializers import (
    LeadSerializer, LeadCreateSerializer, LeadBulkCreateSerializer,
    LeadMetaDataUpdateSerializer, LeadStatsSerializer
)
from .filters import LeadFilter
from .permissions import LeadPermission, LeadBulkPermission
from core.utils.validators import (
    validate_email_strict,
    normalize_phone_e164,
    extract_name,
    _normalize_key,
)
from core.utils.lead_normalization import canonicalize_lead_payload
import uuid
import re
from django.utils import timezone


@extend_schema_view(
    list=extend_schema(
        summary="📞 List leads",
        description="""
        Retrieve all leads in the system with filtering and search capabilities.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can view all leads
        - **✅ Staff/Superuser**: Same access level as regular users
        
        **📊 Shared Lead Database**:
        - All users can view the complete lead database
        - Comprehensive customer information access
        - Universal lead data for call operations
        
        **🎯 Use Cases**:
        - Lead browsing and selection
        - Call planning and preparation
        - Customer data research
        - Lead qualification review
        """,
        responses={
            200: OpenApiResponse(
                response=LeadSerializer(many=True),
                description="✅ Successfully retrieved all leads",
                examples=[
                    OpenApiExample(
                        'Leads List',
                        summary='Available leads for calling',
                        value={
                            'count': 150,
                            'results': [
                                {
                                    'id': 'lead-uuid-1',
                                    'name': 'John',
                                    'surname': 'Smith',
                                    'email': 'john.smith@example.com',
                                    'phone': '+1234567890',
                                    'meta_data': {'industry': 'Technology', 'company': 'TechCorp'},
                                    'created_at': '2024-01-10T09:00:00Z'
                                },
                                {
                                    'id': 'lead-uuid-2',
                                    'name': 'Jane',
                                    'surname': 'Doe',
                                    'email': 'jane.doe@example.com',
                                    'phone': '+1987654321',
                                    'meta_data': {'industry': 'Healthcare', 'position': 'Manager'},
                                    'created_at': '2024-01-12T14:30:00Z'
                                }
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to access leads")
        },
        tags=["Lead Management"]
    ),
    create=extend_schema(
        summary="➕ Create new lead",
        description="""
        Add a new lead to the system for call operations.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can create new leads
        - **✅ Staff/Superuser**: Same access level as regular users
        
        **📝 Lead Information**:
        - Basic contact information (name, email, phone)
        - Custom metadata for lead qualification
        - Flexible data structure for various industries
        
        **💡 Data Entry**:
        - Supports individual lead creation
        - Custom metadata fields for lead qualification
        - Validation for contact information format
        """,
        request=LeadCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=LeadSerializer,
                description="✅ Lead created successfully",
                examples=[
                    OpenApiExample(
                        'New Lead Created',
                        summary='Successfully created lead',
                        value={
                            'id': 'new-lead-uuid',
                            'name': 'Michael',
                            'surname': 'Johnson',
                            'email': 'michael.johnson@company.com',
                            'phone': '+1555123456',
                            'meta_data': {'industry': 'Finance', 'budget': 'High'},
                            'created_at': '2024-01-15T10:30:00Z'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error - Check contact information format"),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Lead Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get lead details",
        description="""
        Retrieve detailed information about a specific lead.
        
        **🔐 Permission Requirements**: All authenticated users can view lead details
        
        **📊 Detailed Information**:
        - Complete lead profile and contact information
        - Custom metadata and qualification details
        - Call history and interaction records
        """,
        responses={
            200: OpenApiResponse(response=LeadSerializer, description="✅ Lead details retrieved successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Lead not found")
        },
        tags=["Lead Management"]
    ),
    update=extend_schema(
        summary="✏️ Update lead",
        description="""
        Update lead information (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot modify existing leads
        - **✅ Staff Members**: Can update any lead information
        - **✅ Superusers**: Can update any lead information
        
        **📝 Data Modification**:
        - Update contact information and metadata
        - Modify lead qualification details
        - Correct data entry errors
        
        **⚠️ Data Quality**:
        - Ensures data consistency across the system
        - Maintains lead database integrity
        - Tracks modification history
        """,
        request=LeadCreateSerializer,
        responses={
            200: OpenApiResponse(response=LeadSerializer, description="✅ Lead updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required for lead modification"),
            404: OpenApiResponse(description="🚫 Lead not found")
        },
        tags=["Lead Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update lead",
        description="""
        Update specific fields of a lead (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        """,
        request=LeadCreateSerializer,
        responses={
            200: OpenApiResponse(response=LeadSerializer, description="✅ Lead updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Lead not found")
        },
        tags=["Lead Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete lead",
        description="""
        Delete a lead from the system (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot delete leads
        - **✅ Staff Members**: Can delete any lead
        - **✅ Superusers**: Can delete any lead
        
        **⚠️ Data Impact**:
        - Removes lead and associated call logs
        - May affect reporting and analytics
        - Consider data archival for compliance
        """,
        responses={
            204: OpenApiResponse(description="✅ Lead deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Lead not found")
        },
        tags=["Lead Management"]
    ),
)
class LeadViewSet(viewsets.ModelViewSet):
    """
    📞 **Lead Management with Shared Access and Staff Controls**
    
    Manages customer leads with universal read access:
    - **👤 All Users**: Can view and create leads (shared database)
    - **👔 Staff**: Can modify and delete leads (data quality control)
    - **🔧 Superusers**: Same as staff for lead operations
    """
    queryset = Lead.objects.all()
    permission_classes = [LeadPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = LeadFilter
    search_fields = ['name', 'surname', 'email', 'phone']
    ordering_fields = ['name', 'surname', 'email', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return LeadCreateSerializer
        return LeadSerializer

    def get_queryset(self):
        """Restrict leads to the active user's workspace context.
        - If `workspace` query param provided and user is member → filter by it
        - Else, if user has exactly one workspace → filter by that
        - Else return empty queryset (no global access)
        """
        qs = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return qs.none()

        # Allow staff/superuser to view across workspaces only when explicit workspace is provided
        requested_ws = self.request.query_params.get('workspace')
        try:
            user_workspaces = getattr(user, 'mapping_user_workspaces', None)
            user_ws_ids = set(str(ws.id) for ws in user_workspaces.all()) if user_workspaces else set()
        except Exception:
            user_ws_ids = set()

        if requested_ws:
            if requested_ws in user_ws_ids or user.is_staff or user.is_superuser:
                return qs.filter(workspace_id=requested_ws)
            return qs.none()

        # No explicit workspace param: infer
        if len(user_ws_ids) == 1:
            only_ws = next(iter(user_ws_ids))
            return qs.filter(workspace_id=only_ws)

        # Multiple or none: do not expose global leads
        return qs.none()
    
    @extend_schema(
        summary="📦 Bulk create leads",
        description="""
        Create multiple leads in a single operation.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can perform bulk lead creation
        - **✅ Staff/Superuser**: Same access level as regular users
        
        **🔄 Bulk Operation Benefits**:
        - Efficient mass data import
        - Batch processing for large datasets
        - Reduced API calls for lead import
        
        **📝 Data Format**:
        - Array of lead objects with same structure as single create
        - Validation applied to each lead individually
        - Partial success supported (some leads may fail)
        
        **💡 Use Cases**:
        - CSV/Excel file imports
        - CRM system migrations
        - Lead list uploads
        - Batch data entry operations
        """,
        request=LeadBulkCreateSerializer,
        responses={
            201: OpenApiResponse(
                description="✅ Bulk lead creation completed",
                examples=[
                    OpenApiExample(
                        'Bulk Create Results',
                        summary='Multiple leads created with results',
                        value={
                            'total_leads': 100,
                            'successful_creates': 95,
                            'failed_creates': 5,
                            'errors': [
                                {'index': 12, 'error': 'Invalid email format'},
                                {'index': 45, 'error': 'Phone number already exists'}
                            ],
                            'created_lead_ids': ['uuid1', 'uuid2', 'uuid3']
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error - Check lead data format"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied")
        },
        tags=["Lead Management"]
    )
    
    def _process_csv_columns_to_variables(self, detected_keys: set) -> dict:
        """Convert detected CSV column names to custom_variables format"""
        variables = {
            'variables': []
        }
        
        for key in sorted(detected_keys):
            variable_def = {
                'key': key,
                'label': key.replace('_', ' ').title(),
                'type': 'string',  # CSV columns are always strings initially
                'source': 'csv'
            }
            
            variables['variables'].append(variable_def)
        
        return variables
    
    @action(detail=False, methods=['post'], permission_classes=[LeadBulkPermission])
    def bulk_create(self, request):
        """Create multiple leads in bulk with CSV-style mapping and batch tagging."""
        serializer = LeadBulkCreateSerializer(data=request.data)

        # Prefer raw list from request for CSV-style flexible payloads
        raw_leads = request.data.get('leads', None)
        if isinstance(raw_leads, list):
            pass
        else:
            # Fallback to strict validation path if no raw list provided
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            raw_leads = serializer.validated_data['leads']

        # Determine workspace auto-assignment (exactly one workspace for user)
        user = request.user
        assigned_workspace = None
        try:
            workspaces_qs = getattr(user, 'mapping_user_workspaces', None)
            if workspaces_qs is not None and workspaces_qs.count() == 1:
                assigned_workspace = workspaces_qs.first()
        except Exception:
            assigned_workspace = None

        # Enforce hard limit of 10,000 rows per CSV/bulk import
        try:
            if isinstance(raw_leads, list) and len(raw_leads) > 10000:
                return Response(
                    {'error': 'CSV import exceeds 10,000 rows limit'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception:
            pass

        # Generate one batch id for this upload
        import_batch_id = str(uuid.uuid4())

        created_leads = []
        errors = []
        detected_variable_keys = set()
        all_csv_columns = set()  # NEW: Collect ALL column names

        # Field synonym sets aligned with Meta mapping logic
        PERSON_NAME_FIELDS = {
            'first_name', 'given_name', 'vorname', 'prenom', 'nombre',
            'firstname', 'fname', 'forename', 'first'
        }
        PERSON_SURNAME_FIELDS = {
            'last_name', 'family_name', 'nachname', 'nom', 'apellido',
            'lastname', 'lname', 'surname', 'family', 'last'
        }
        FULL_NAME_FIELDS = {
            'full_name', 'fullname', 'name', 'display_name', 'person_name',
            'customer_name', 'user_name', 'client_name', 'contact_name',
            'vollstandiger_name', 'kontakt_name'
        }
        EMAIL_FIELDS = {
            'email', 'email_address', 'e_mail', 'mail', 'contact_email',
            'user_email', 'customer_email', 'business_email', 'work_email',
            'email_adresse', 'e_mail_adresse', 'emailadresse', 'kontakt_email',
            'kontaktmail'
        }
        PHONE_FIELDS = {
            'phone', 'phone_number', 'telephone', 'telefon', 'mobile',
            'cell', 'handy', 'contact_phone', 'mobile_number', 'cell_phone',
            'phone_mobile', 'tel', 'telefonnummer', 'telefon_nummer',
            'geschaftliche_telefonnummer', 'business_phone', 'work_phone',
            'telefono', 'telefone', 'handynummer'
        }

        # Canonical mapping for common business CSV fields (DE/EN -> EN canonical)
        CANONICAL_CUSTOM_KEYS = {
            # Company
            'firma': 'company',
            'unternehmen': 'company',
            'unternehmensname': 'company',
            'company': 'company',
            'company_name': 'company',
            'firmenname': 'company',
            # Industry / Branche
            'branche': 'industry',
            'industrie': 'industry',
            'industry': 'industry',
            'sektor': 'industry',
            # Employee count
            'mitarbeiteranzahl': 'employee_count',
            'anzahl_mitarbeiter': 'employee_count',
            'mitarbeiter': 'employee_count',
            'employees': 'employee_count',
            'employee_count': 'employee_count',
            # Budget
            'budget': 'budget',
        }

        for index, row in enumerate(raw_leads):
            try:
                # Fast path: use canonical normalization for provider-agnostic mapping
                if isinstance(row, dict):
                    # NEW: Collect ALL original column names from this row
                    for k in row.keys():
                        if k:
                            all_csv_columns.add(str(k))
                    
                    normalized = canonicalize_lead_payload(row)
                    first_name = (normalized.get('first_name') or '').strip()
                    last_name = (normalized.get('last_name') or '').strip()
                    email_to_save = (normalized.get('email') or '').strip()
                    phone_to_save = (normalized.get('phone') or '').strip()
                    variables = normalized.get('variables') or {}

                    if first_name and email_to_save and phone_to_save:
                        if variables:
                            detected_variable_keys.update(variables.keys())
                        meta_data = {
                            'source': 'csv',
                            'import_batch_id': import_batch_id,
                        }
                        lead = Lead.objects.create(
                            name=first_name,
                            surname=last_name or '',
                            email=email_to_save,
                            phone=phone_to_save,
                            workspace=assigned_workspace if isinstance(assigned_workspace, Workspace) else None,
                            integration_provider='manual',
                            variables=variables,
                            meta_data=meta_data,
                        )
                        created_leads.append(lead)
                        continue
                else:
                    errors.append({'index': index, 'error': 'Invalid row format'})
                    continue

                # Legacy fallback (kept for robustness)
                # Normalize keys and collect pairs
                pairs = []  # List[Tuple[str, str]]
                for k, v in row.items():
                    if v is None:
                        continue
                    v_str = str(v).strip()
                    if not v_str:
                        continue
                    k_norm = _normalize_key(str(k))
                    pairs.append((k_norm, v_str))
                    
                    # NEW: Collect original column name for funnel variables
                    all_csv_columns.add(str(k))

                # Pick candidates similar to Meta mapping
                first = next((v for k, v in pairs if k in PERSON_NAME_FIELDS and v), '')
                last = next((v for k, v in pairs if k in PERSON_SURNAME_FIELDS and v), '')
                full = next((v for k, v in pairs if k in FULL_NAME_FIELDS and v), '')

                # Heuristic: any key containing "name" but not business tokens
                if not full:
                    BUSINESS_TOKENS = {'company', 'business', 'firma', 'unternehmen', 'organization', 'org', 'brand'}
                    for k, v in pairs:
                        if 'name' in k and not any(tok in k for tok in BUSINESS_TOKENS):
                            full = v
                            break

                # Email detection
                email_val = None
                email_key = None
                raw_email_fallback = None
                for k, v in pairs:
                    if k in EMAIL_FIELDS:
                        e = validate_email_strict(v)
                        if e:
                            email_val = e
                            email_key = k
                            break
                if not email_val:
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
                            # Keep raw as fallback, also try strict
                            raw_email_fallback = v
                            e = validate_email_strict(v)
                            if e:
                                email_val = e
                                email_key = k
                                break

                # Phone detection
                phone_val = None
                phone_key = None
                raw_phone_candidate = None
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
                if not phone_val:
                    # Fallback: accept first phone-like string (prefer known phone fields), minimal sanitization
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
                        raw_phone_candidate = candidate

                # Name resolution
                name_first = ''
                name_surname = ''
                name_triplet = extract_name(first, last, full)
                if name_triplet:
                    name_first, name_surname, _ = name_triplet
                else:
                    # Fallback: if only full exists
                    if full:
                        name_first = full
                # Validate presence (Meta-like tolerance): allow raw fallbacks if strict failed
                email_to_save = email_val or raw_email_fallback or ''
                phone_to_save = phone_val or raw_phone_candidate or ''

                # Validate required fields (must have name + email + phone, but email/phone may be raw)
                if not (name_first and email_to_save and phone_to_save):
                    errors.append({
                        'index': index,
                        'error': 'Missing or invalid required fields (name/email/phone)'
                    })
                    continue

                # Build variables from remaining keys
                used_keys = {k for k in [email_key, phone_key] if k}
                # Mark name-related keys as used
                used_keys.update(PERSON_NAME_FIELDS)
                used_keys.update(PERSON_SURNAME_FIELDS)
                used_keys.update(FULL_NAME_FIELDS)

                variables = {}
                for k, v in pairs:
                    if k not in used_keys:
                        canonical_k = CANONICAL_CUSTOM_KEYS.get(k, k)
                        variables[canonical_k] = v

                if variables:
                    detected_variable_keys.update(variables.keys())

                meta_data = {
                    'source': 'csv',
                    'import_batch_id': import_batch_id,
                }

                lead = Lead.objects.create(
                    name=name_first,
                    surname=name_surname or '',
                    email=email_to_save,
                    phone=phone_to_save,
                    workspace=assigned_workspace if isinstance(assigned_workspace, Workspace) else None,
                    integration_provider='manual',
                    variables=variables,
                    meta_data=meta_data,
                )
                created_leads.append(lead)

            except Exception as e:
                errors.append({'index': index, 'error': str(e)})

        # If we successfully created leads and have a clear workspace, create a LeadFunnel for this CSV batch
        lead_funnel_id = None
        if created_leads and isinstance(assigned_workspace, Workspace):
            try:
                funnel_name = f"CSV Import {timezone.now().strftime('%Y-%m-%d %H:%M')} ({len(created_leads)} Leads)"
                
                # Process ALL collected column names for funnel variables
                final_column_names = set()
                for raw_column in all_csv_columns:
                    # Normalize and apply canonical mapping
                    normalized = _normalize_key(raw_column).lower()  # Ensure lowercase
                    canonical = CANONICAL_CUSTOM_KEYS.get(normalized, normalized)
                    final_column_names.add(canonical)
                
                # Create funnel variables from all columns
                csv_variables = self._process_csv_columns_to_variables(final_column_names)
                
                funnel = LeadFunnel.objects.create(
                    name=funnel_name,
                    workspace=assigned_workspace,
                    is_active=True,
                    custom_variables=csv_variables,
                )
                lead_funnel_id = str(funnel.id)
                # Attach all created leads to this funnel in bulk
                Lead.objects.filter(id__in=[lead.id for lead in created_leads]).update(lead_funnel=funnel)
            except Exception:
                # If funnel creation fails, proceed without blocking the import
                lead_funnel_id = None

        response_payload = {
            'total_leads': len(raw_leads),
            'successful_creates': len(created_leads),
            'failed_creates': len(errors),
            'errors': errors,
            'created_lead_ids': [str(lead.id) for lead in created_leads],
            'import_batch_id': import_batch_id,
            'detected_variable_keys': sorted(list(detected_variable_keys)),
        }
        # Additive, optional field: helps frontend to show the CSV source in Agent Config
        if lead_funnel_id:
            response_payload['lead_funnel_id'] = lead_funnel_id

        return Response(response_payload, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary="🏷️ Update lead metadata",
        description="""
        Update custom metadata fields for a lead (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot modify lead metadata
        - **✅ Staff Members**: Can update metadata for any lead
        - **✅ Superusers**: Can update metadata for any lead
        
        **📝 Metadata Management**:
        - Update custom fields and qualifications
        - Add industry-specific information
        - Modify lead scoring and categorization
        
        **🎯 Use Cases**:
        - Lead qualification updates
        - Campaign tag additions
        - Data enrichment operations
        - Quality scoring modifications
        """,
        request=LeadMetaDataUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=LeadSerializer,
                description="✅ Lead metadata updated successfully",
                examples=[
                    OpenApiExample(
                        'Metadata Updated',
                        summary='Lead metadata successfully modified',
                        value={
                            'id': 'lead-uuid',
                            'name': 'John Smith',
                            'meta_data': {
                                'industry': 'Technology',
                                'company_size': 'Enterprise',
                                'lead_score': 85,
                                'campaign': 'Q1-2024-Tech',
                                'qualification_status': 'qualified'
                            },
                            'updated_at': '2024-01-15T11:00:00Z'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Lead not found")
        },
        tags=["Lead Management"]
    )
    @action(detail=True, methods=['patch'], permission_classes=[LeadPermission])
    def update_metadata(self, request, pk=None):
        """Update lead metadata (staff only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can update lead metadata'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        lead = self.get_object()
        serializer = LeadMetaDataUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            lead.meta_data.update(serializer.validated_data['meta_data'])
            lead.save()
            
            return Response(LeadSerializer(lead).data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="📞 Get lead call history",
        description="""
        Retrieve all call logs associated with a specific lead.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can view call history for any lead
        
        **📊 Call Information**:
        - Complete call history and interactions
        - Call outcomes and duration details
        - Agent and phone number information
        - Call timestamps and directions
        
        **🎯 Use Cases**:
        - Lead interaction review
        - Call outcome analysis
        - Agent performance tracking
        - Customer communication history
        """,
        responses={
            200: OpenApiResponse(
                description="✅ Lead call history retrieved successfully",
                examples=[
                    OpenApiExample(
                        'Call History',
                        summary='Lead interaction history',
                        value={
                            'lead_id': 'lead-uuid',
                            'lead_name': 'John Smith',
                            'total_calls': 3,
                            'call_logs': [
                                {
                                    'id': 'call-uuid-1',
                                    'timestamp': '2024-01-15T09:30:00Z',
                                    'direction': 'outbound',
                                    'duration': 180,
                                    'from_number': '+1234567890',
                                    'to_number': '+1987654321',
                                    'disconnection_reason': 'completed'
                                }
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Lead not found")
        },
        tags=["Lead Management"]
    )
    @action(detail=True, methods=['get'])
    def call_history(self, request, pk=None):
        """Get call history for a lead"""
        lead = self.get_object()
        call_logs = CallLog.objects.filter(lead=lead).order_by('-timestamp')
        
        # Import CallLogSerializer here to avoid circular imports
        from core.management_api.call_api.serializers import CallLogSerializer
        
        call_logs_data = CallLogSerializer(call_logs, many=True).data
        
        return Response({
            'lead_id': str(lead.id),
            'lead_name': f"{lead.name} {lead.surname}".strip(),
            'total_calls': call_logs.count(),
            'call_logs': call_logs_data
        })
    
    @extend_schema(
        summary="📈 Get lead statistics",
        description="""
        Retrieve comprehensive statistics and analytics for leads.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can view lead statistics
        
        **📊 Statistics Included**:
        - Total lead count and growth trends
        - Lead source and qualification breakdown
        - Call conversion rates and outcomes
        - Industry and demographic analytics
        
        **🎯 Business Intelligence**:
        - Lead generation performance
        - Conversion funnel analysis
        - Campaign effectiveness metrics
        - Agent performance correlation
        """,
        responses={
            200: OpenApiResponse(
                response=LeadStatsSerializer,
                description="✅ Lead statistics retrieved successfully",
                examples=[
                    OpenApiExample(
                        'Lead Statistics',
                        summary='Comprehensive lead analytics',
                        value={
                            'total_leads': 1250,
                            'leads_this_month': 85,
                            'qualified_leads': 340,
                            'contacted_leads': 890,
                            'conversion_rate': 27.2,
                            'avg_calls_per_lead': 2.3,
                            'top_industries': ['Technology', 'Healthcare', 'Finance'],
                            'lead_sources': {'website': 450, 'referral': 300, 'social': 200}
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Lead Management"]
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get lead statistics"""
        from django.db.models import Count, Avg
        
        try:
            total_leads = Lead.objects.count()
            
            # Calculate basic statistics with error handling
            stats = {
                'total_leads': total_leads,
                'leads_with_calls': 0,
                'leads_without_calls': total_leads,
                'avg_calls_per_lead': None
            }
            
            # Try to get call statistics - handle potential database schema issues
            try:
                leads_with_calls = Lead.objects.filter(mapping_lead_calllogs__isnull=False).distinct().count()
                leads_without_calls = Lead.objects.filter(mapping_lead_calllogs__isnull=True).count()
                
                stats.update({
                    'leads_with_calls': leads_with_calls,
                    'leads_without_calls': leads_without_calls,
                })
                
                # Add call statistics if available
                if total_leads > 0:
                    call_stats = Lead.objects.aggregate(
                        avg_calls_per_lead=Avg('mapping_lead_calllogs__id')
                    )
                    if call_stats.get('avg_calls_per_lead') is not None:
                        stats['avg_calls_per_lead'] = call_stats['avg_calls_per_lead']
                        
            except Exception as e:
                # Log the error but continue with basic stats
                print(f"Warning: Could not calculate call statistics: {e}")
            
            serializer = LeadStatsSerializer(data=stats)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data)
            
        except Exception as e:
            # Return basic fallback stats if there are database issues
            fallback_stats = {
                'total_leads': 0,
                'leads_with_calls': 0,
                'leads_without_calls': 0,
                'avg_calls_per_lead': None
            }
            serializer = LeadStatsSerializer(data=fallback_stats)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data) 