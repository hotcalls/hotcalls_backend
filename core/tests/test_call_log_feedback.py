import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch

from core.models import (
    Workspace,
    Agent,
    Lead,
    CallTask,
    CallStatus,
    DisconnectionReason,
)
from core.tasks import update_calltask_from_calllog


@pytest.mark.django_db
def _setup_agent_lead_task():
    ws = Workspace.objects.create(workspace_name="WS")
    agent = Agent.objects.create(
        workspace=ws,
        name="Agent",
        status="active",
        language="de",
        retry_interval=30,
        max_retries=3,
        workdays=["monday"],
        call_from="09:00:00",
        call_to="17:00:00",
        character="",
        prompt="",
    )
    lead = Lead.objects.create(
        workspace=ws,
        name="Max",
        surname="Mustermann",
        email="max@example.com",
        phone="+49123456789",
    )
    task = CallTask.objects.create(
        workspace=ws,
        agent=agent,
        lead=lead,
        phone=lead.phone,
        status=CallStatus.IN_PROGRESS,
        attempts=0,
        next_call=None,
    )
    return ws, agent, lead, task


def _auth_staff_client():
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(email="staff@example.com", password="x", is_staff=True)
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    "reason, expect_deleted, expect_attempts_delta, expect_status",
    [
        (DisconnectionReason.USER_HANGUP, True, 0, None),  # success → deleted
        (DisconnectionReason.INVALID_DESTINATION, True, 0, None),  # permanent → deleted
        (DisconnectionReason.DIAL_NO_ANSWER, False, 1, CallStatus.RETRY),  # retry + increment
        (DisconnectionReason.ERROR_NO_AUDIO_RECEIVED, False, 0, CallStatus.RETRY),  # retry no increment
    ],
)
def test_call_log_feedback_linked_by_id(reason, expect_deleted, expect_attempts_delta, expect_status):
    ws, agent, lead, task = _setup_agent_lead_task()

    client = _auth_staff_client()

    payload = {
        "lead": str(lead.id),
        "agent": str(agent.agent_id),
        "from_number": "+49000000001",
        "to_number": lead.phone,
        "duration": 42,
        "disconnection_reason": reason,
        "direction": "outbound",
        "status": "completed",
        "appointment_datetime": None,
        "calltask_id": str(task.id),
    }

    # Patch delay to call synchronously
    with patch(
        "core.management_api.call_api.views.update_calltask_from_calllog.delay",
        side_effect=lambda call_log_id, calltask_id: update_calltask_from_calllog(call_log_id, calltask_id),
    ):
        resp = client.post("/api/calls/call-logs/", payload, format="json")
        assert resp.status_code == 201

    # Reload or check deletion
    if expect_deleted:
        assert not CallTask.objects.filter(id=task.id).exists()
    else:
        updated = CallTask.objects.get(id=task.id)
        assert updated.attempts == task.attempts + expect_attempts_delta
        assert updated.status == expect_status


@pytest.mark.django_db
def test_call_log_requires_calltask_id():
    ws, agent, lead, task = _setup_agent_lead_task()
    client = _auth_staff_client()

    payload = {
        "lead": str(lead.id),
        "agent": str(agent.agent_id),
        "from_number": "+49000000001",
        "to_number": lead.phone,
        "duration": 42,
        "disconnection_reason": DisconnectionReason.DIAL_NO_ANSWER,
        "direction": "outbound",
        "status": "completed",
        "appointment_datetime": None,
        # missing calltask_id
    }

    resp = client.post("/api/calls/call-logs/", payload, format="json")
    assert resp.status_code == 400

