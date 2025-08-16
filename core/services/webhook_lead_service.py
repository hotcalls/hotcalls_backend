import logging
from typing import Dict, Optional
from django.db import transaction
from django.utils import timezone
from core.utils.lead_normalization import canonicalize_lead_payload

from core.models import (
    Lead, LeadFunnel, WebhookLeadSource, CallTask, CallStatus
)

logger = logging.getLogger(__name__)


class WebhookLeadService:
    """
    Processes incoming webhook leads for custom webhook sources.
    Mirrors Meta behavior: accept only when funnel + agent are active, and
    create a CallTask immediately when a Lead is created.
    """

    @staticmethod
    def _update_lead_stats(workspace, reason: str):
        from core.models import LeadProcessingStats
        today = timezone.now().date()
        stats, _ = LeadProcessingStats.objects.get_or_create(workspace=workspace, date=today)
        stats.total_received += 1
        if reason == 'processed':
            stats.processed_with_agent += 1
        elif reason == 'no_agent':
            stats.ignored_no_agent += 1
        elif reason == 'agent_inactive':
            stats.ignored_inactive_agent += 1
        elif reason == 'funnel_inactive':
            stats.ignored_inactive_funnel += 1
        elif reason == 'no_funnel':
            stats.ignored_no_funnel += 1
        stats.save()

    @transaction.atomic
    def process_incoming_lead(self, payload: Dict, source: WebhookLeadSource) -> Dict:
        """
        Validates gating and creates Lead + CallTask atomically.

        Returns a dict with status and optional lead_id.
        """
        lead_funnel: LeadFunnel = source.lead_funnel
        workspace = source.workspace

        # Gate checks
        if not lead_funnel:
            self._update_lead_stats(workspace, 'no_funnel')
            return {"status": "ignored_no_funnel"}
        if not lead_funnel.is_active:
            self._update_lead_stats(workspace, 'funnel_inactive')
            return {"status": "ignored_inactive_funnel"}
        if not hasattr(lead_funnel, 'agent') or not lead_funnel.agent:
            self._update_lead_stats(workspace, 'no_agent')
            return {"status": "ignored_no_agent"}

        agent = lead_funnel.agent
        if agent.status != 'active':
            self._update_lead_stats(workspace, 'agent_inactive')
            return {"status": "ignored_inactive_agent"}

        # Canonical normalization of inbound fields
        normalized = canonicalize_lead_payload(payload or {})
        name = normalized.get('first_name') or ''
        surname = normalized.get('last_name') or ''
        email = normalized.get('email') or ''
        phone = normalized.get('phone') or ''
        variables = normalized.get('variables') or {}
        external_id = payload.get('external_id')

        # Simple idempotency: if external_id provided, avoid duplicates per funnel
        if external_id:
            existing = Lead.objects.filter(
                lead_funnel=lead_funnel,
                variables__external_id=external_id,
            ).first()
            if existing:
                logger.info("Duplicate webhook lead ignored (external_id)", extra={
                    'lead_id': str(existing.id),
                    'funnel_id': str(lead_funnel.id),
                    'external_id': external_id,
                })
                # Do not change stats counters again (counted as received only once ideally)
                return {"status": "duplicate", "lead_id": str(existing.id)}

        # Create Lead
        lead = Lead.objects.create(
            name=name or 'Webhook Lead',
            surname=surname or '',
            email=email or f'lead-{timezone.now().timestamp()}@webhook.local',
            phone=phone or '',
            workspace=workspace,
            integration_provider='custom-webhook',
            variables={**variables, **({'external_id': external_id} if external_id else {})},
            lead_funnel=lead_funnel,
        )

        # Create CallTask immediately
        try:
            CallTask.objects.create(
                status=CallStatus.SCHEDULED,
                attempts=0,
                phone=lead.phone,
                workspace=workspace,
                lead=lead,
                agent=agent,
                next_call=timezone.now(),
            )
            self._update_lead_stats(workspace, 'processed')
        except Exception as e:
            logger.error("Failed to create CallTask for webhook lead", extra={
                'lead_id': str(lead.id), 'error': str(e), 'workspace_id': str(workspace.id)
            })

        return {"status": "processed_with_agent", "lead_id": str(lead.id)}


