import logging
from typing import Dict, Optional
from django.db import transaction
from django.utils import timezone
from core.utils.validators import normalize_phone_e164

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
    def process_incoming_lead(self, lead_data: Dict, webhook: WebhookLeadSource) -> Dict:
        """
        Validates gating and creates Lead + CallTask atomically.

        Returns a dict with status and optional lead_id.
        """
        lead_funnel = webhook.lead_funnel
        workspace = webhook.workspace

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
        name = lead_data['name']
        surname = lead_data['surname']
        email = lead_data['email']

        phone_number = lead_data['phone_number']
        phone_normalized = normalize_phone_e164(phone_number, default_region='DE')
        phone_to_save = phone_normalized or phone_number

        variables = lead_data.get('custom_variables')

        # Create Lead
        lead = Lead.objects.create(
            name=name or 'Webhook Lead',
            surname=surname or '',
            email=email or f'lead-{timezone.now().timestamp()}@webhook.local',
            phone=phone_to_save or '',
            workspace=workspace,
            integration_provider='custom-webhook',
            variables=variables,
            lead_funnel=lead_funnel,
        )

        # Create CallTask immediately – honor agent working hours via central util
        try:
            from core.utils.calltask_utils import create_call_task_safely
            create_call_task_safely(
                agent=agent,
                workspace=workspace,
                target_ref=f"lead:{lead.id}",
            )
            self._update_lead_stats(workspace, 'processed')
        except Exception as e:
            logger.error("Failed to create CallTask for webhook lead", extra={
                'lead_id': str(lead.id), 'error': str(e), 'workspace_id': str(workspace.id)
            })

        return {"status": "processed_with_agent", "lead_id": str(lead.id)}


