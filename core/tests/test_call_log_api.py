import hashlib
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Workspace, Agent, Lead, CallTask, CallStatus, DisconnectionReason, LiveKitAgent


def _staff_client():
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(email="staff@example.com", password="x", is_staff=True)
    client = APIClient()
    client.force_authenticate(user)
    return client


def _user_client():
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(email="user@example.com", password="x", is_staff=False)
    client = APIClient()
    client.force_authenticate(user)
    return client


def _mk_env():
    ws = Workspace.objects.create(workspace_name="WS")
    agent = Agent.objects.create(
        workspace=ws,
        name="Agent",
        status="active",
        language="de",
        retry_interval=30,
        max_retries=2,
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
        next_call=timezone.now(),
    )
    return ws, agent, lead, task


@pytest.mark.django_db
def test_call_log_staff_auth_success():
    ws, agent, lead, task = _mk_env()
    client = _staff_client()
    payload = {
        "lead": str(lead.id),
        "agent": str(agent.agent_id),
        "from_number": "+49000000001",
        "to_number": lead.phone,
        "duration": 60,
        "disconnection_reason": DisconnectionReason.USER_HANGUP.value,
        "direction": "outbound",
        "appointment_datetime": None,
        "calltask_id": str(task.id),
    }
    # patch delay to sync
    with patch("core.tasks.update_calltask_from_calllog.delay", side_effect=lambda a, b: None):
        resp = client.post("/api/calls/call-logs/", payload, format="json")
        assert resp.status_code == 201


@pytest.mark.django_db
def test_call_log_livekit_header_success():
    ws, agent, lead, task = _mk_env()
    # Create valid LiveKitAgent token
    lka = LiveKitAgent.objects.create(name="hotcalls_agent", token="sekret-token")
    client = APIClient()
    payload = {
        "lead": str(lead.id),
        "agent": str(agent.agent_id),
        "from_number": "+49000000001",
        "to_number": lead.phone,
        "duration": 60,
        "disconnection_reason": DisconnectionReason.USER_HANGUP.value,
        "direction": "outbound",
        "appointment_datetime": None,
        "calltask_id": str(task.id),
    }
    with patch("core.tasks.update_calltask_from_calllog.delay", side_effect=lambda a, b: None):
        resp = client.post(
            "/api/calls/call-logs/", payload, format="json", HTTP_X_LIVEKIT_TOKEN=lka.token
        )
        assert resp.status_code == 201


@pytest.mark.django_db
def test_call_log_forbidden_without_staff_or_livekit():
    ws, agent, lead, task = _mk_env()
    client = _user_client()
    payload = {
        "lead": str(lead.id),
        "agent": str(agent.agent_id),
        "from_number": "+49000000001",
        "to_number": lead.phone,
        "duration": 60,
        "disconnection_reason": DisconnectionReason.USER_HANGUP.value,
        "direction": "outbound",
        "appointment_datetime": None,
        "calltask_id": str(task.id),
    }
    resp = client.post("/api/calls/call-logs/", payload, format="json")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_call_log_validation_status_requires_appointment_datetime():
    ws, agent, lead, task = _mk_env()
    client = _staff_client()
    payload = {
        "lead": str(lead.id),
        "agent": str(agent.agent_id),
        "from_number": "+49000000001",
        "to_number": lead.phone,
        "duration": 60,
        "disconnection_reason": DisconnectionReason.USER_HANGUP.value,
        "direction": "outbound",
        "status": "appointment_scheduled",
        # missing appointment_datetime
        "calltask_id": str(task.id),
    }
    resp = client.post("/api/calls/call-logs/", payload, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_call_log_validation_appointment_datetime_only_for_appointment_status():
    ws, agent, lead, task = _mk_env()
    client = _staff_client()
    payload = {
        "lead": str(lead.id),
        "agent": str(agent.agent_id),
        "from_number": "+49000000001",
        "to_number": lead.phone,
        "duration": 60,
        "disconnection_reason": DisconnectionReason.USER_HANGUP.value,
        "direction": "outbound",
        "status": "completed",
        "appointment_datetime": timezone.now().isoformat(),
        "calltask_id": str(task.id),
    }
    resp = client.post("/api/calls/call-logs/", payload, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_quota_recording_called():
    ws, agent, lead, task = _mk_env()
    client = _staff_client()
    payload = {
        "lead": str(lead.id),
        "agent": str(agent.agent_id),
        "from_number": "+49000000001",
        "to_number": lead.phone,
        "duration": 120,  # 2 minutes
        "disconnection_reason": DisconnectionReason.USER_HANGUP.value,
        "direction": "outbound",
        "calltask_id": str(task.id),
    }
    with patch("core.quotas.enforce_and_record") as mock_enforce, patch(
        "core.tasks.update_calltask_from_calllog.delay", side_effect=lambda a, b: None
    ):
        resp = client.post("/api/calls/call-logs/", payload, format="json")
        assert resp.status_code == 201
        # amount in minutes
        args, kwargs = mock_enforce.call_args
        assert kwargs["workspace"] == agent.workspace
        assert float(kwargs["amount"]) == pytest.approx(2.0)


@pytest.mark.django_db
def test_schema_endpoint_ok():
    client = _staff_client()
    resp = client.get("/api/schema/")
    # 200 or 403 depending on schema access; ensure not 500
    assert resp.status_code in (200, 403)


