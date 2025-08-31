import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

# ⚠️ adjust imports if your app labels differ
from core.models import CallLog, CallTask, Agent, Lead  # workspace/phone models not required for these tests

ENDPOINT = "/api/calls/end-of-call/"
VALID_TOKEN = "TEST_LK_TOKEN"


def _payload(call_task_id, **overrides):
    """Base payload helper."""
    base = {
        "call_task_id": str(call_task_id),
        "disconnection_reason": "user_hangup",
        "event_id": str(uuid.uuid4()),
        # NOTE: direction is optional; serializer/view should default to 'outbound'
        # "direction": "outbound",
        # "appointment_datetime": "2025-08-20T12:00:00Z",
    }
    base.update(overrides)
    return base


class EndOfCallEndpointTests(TestCase):
    """
    Covers:
      - happy path (LiveKit token, event_id present)
      - idempotency duplicate (second POST returns 200, no new CallLog, usage not double-charged)
      - legacy (no event_id)
      - auth/permissions (no token; staff allowed)
      - validation errors
      - unknown fields ignored
      - race (IntegrityError path)
      - list sanity (result appears in /api/calls/call-logs/)
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user(
            email="staff@example.com",
            password="x",
            first_name="Staff",
            last_name="User",
            phone="+4912345678",
            is_staff=True,
        )

        # Minimal fixtures required by your serializer/create logic
        # Create a workspace
        from core.models import Workspace, PhoneNumber, SIPTrunk, CallStatus
        cls.workspace = Workspace.objects.create(workspace_name="Test WS")

        # Create phone infrastructure
        trunk = SIPTrunk.objects.create(
            provider_name="TestProvider",
            sip_username="u",
            sip_password="p",
            sip_host="host",
            sip_port=5060,
        )
        phone_number = PhoneNumber.objects.create(phonenumber="+49999999999", sip_trunk=trunk)

        # Agent requires many fields
        cls.agent = Agent.objects.create(
            workspace=cls.workspace,
            name="Agent Zero",
            status="active",
            greeting_inbound="hi",
            greeting_outbound="hi",
            language="en",
            retry_interval=1,
            max_retries=3,
            workdays=["monday", "tuesday"],
            call_from="09:00:00",
            call_to="17:00:00",
            character="friendly",
            script_template="do it",
            phone_number=phone_number,
        )

        cls.lead = Lead.objects.create(name="Max", surname="Mustermann", email="max@example.com", phone="+4900000", workspace=cls.workspace)

        # Create a CallTask ~ 2 minutes ago (duration > 0)
        from django.utils import timezone
        from datetime import timedelta
        cls.call_task = CallTask.objects.create(
            id=uuid.uuid4(),
            lead=cls.lead,
            agent=cls.agent,
            workspace=cls.workspace,
            phone="+4917012345678",
            created_at=timezone.now() - timedelta(seconds=120),
            next_call=timezone.now(),
            status=getattr(CallStatus, "IN_PROGRESS", "in_progress"),
        )

    def setUp(self):
        self.client = APIClient()

    # ---------------- AUTH ----------------

    def test_forbidden_without_token_and_not_staff(self):
        resp = self.client.post(ENDPOINT, data={}, format="json")
        self.assertIn(resp.status_code, (401, 403))

    def test_staff_can_post(self):
        self.client.force_authenticate(user=self.staff)
        payload = _payload(self.call_task.id)

        # Patch the small helper we added in the view so we don't care about workspaces/quotas in this test
        with patch("core.management_api.call_api.views._record_usage_minutes") as usage, \
             patch("core.tasks.update_calltask_from_calllog.delay") as enqueue:
            resp = self.client.post(ENDPOINT, data=payload, format="json")

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(CallLog.objects.count(), 1)
        usage.assert_called_once()
        enqueue.assert_called_once()

    # LiveKit token path → patch permission (we’re not validating the token itself here)
    @patch("core.management_api.call_api.permissions.CallLogPermission.has_permission", return_value=True)
    def test_happy_path_with_livekit_token_and_event_id(self, _perm):
        headers = {"HTTP_X_LIVEKIT_TOKEN": VALID_TOKEN}
        payload = _payload(self.call_task.id, event_id=str(uuid.uuid4()))

        with patch("core.management_api.call_api.views._record_usage_minutes") as usage, \
             patch("core.tasks.update_calltask_from_calllog.delay") as enqueue:
            resp = self.client.post(ENDPOINT, data=payload, format="json", **headers)

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(CallLog.objects.count(), 1)
        log = CallLog.objects.get()
        self.assertEqual(str(log.call_task_id), str(self.call_task.id))
        # default direction should be 'outbound' when omitted
        self.assertEqual(getattr(log, "direction", "outbound"), "outbound")
        self.assertGreater(getattr(log, "duration", 0), 0)
        usage.assert_called_once()
        enqueue.assert_called_once()

    # ---------------- IDEMPOTENCY ----------------

    @patch("core.management_api.call_api.permissions.CallLogPermission.has_permission", return_value=True)
    def test_idempotent_duplicate_event_id_returns_200_no_new_log(self, _perm):
        headers = {"HTTP_X_LIVEKIT_TOKEN": VALID_TOKEN}
        eid = str(uuid.uuid4())
        payload = _payload(self.call_task.id, event_id=eid)

        with patch("core.management_api.call_api.views._record_usage_minutes") as usage, \
             patch("core.tasks.update_calltask_from_calllog.delay") as enqueue:
            resp1 = self.client.post(ENDPOINT, data=payload, format="json", **headers)
            resp2 = self.client.post(ENDPOINT, data=payload, format="json", **headers)

        self.assertEqual(resp1.status_code, 201)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(CallLog.objects.count(), 1)
        # usage recorded exactly once
        usage.assert_called_once()
        # enqueue called on fresh create and again on duplicate (since task not terminal)
        self.assertEqual(enqueue.call_count, 2)

    # ---------------- LEGACY (no event_id) ----------------

    @patch("core.management_api.call_api.permissions.CallLogPermission.has_permission", return_value=True)
    def test_legacy_no_event_id_creates_log(self, _perm):
        headers = {"HTTP_X_LIVEKIT_TOKEN": VALID_TOKEN}
        payload = _payload(self.call_task.id)
        payload.pop("event_id", None)

        with patch("core.management_api.call_api.views._record_usage_minutes") as usage, \
             patch("core.tasks.update_calltask_from_calllog.delay") as enqueue:
            resp = self.client.post(ENDPOINT, data=payload, format="json", **headers)

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(CallLog.objects.count(), 1)
        usage.assert_called_once()
        enqueue.assert_called_once()

    # ---------------- VALIDATION ----------------

    @patch("core.management_api.call_api.permissions.CallLogPermission.has_permission", return_value=True)
    def test_missing_call_task_id_400(self, _perm):
        headers = {"HTTP_X_LIVEKIT_TOKEN": VALID_TOKEN}
        payload = {"disconnection_reason": "user_hangup", "event_id": str(uuid.uuid4())}
        resp = self.client.post(ENDPOINT, data=payload, format="json", **headers)
        self.assertEqual(resp.status_code, 400)

    @patch("core.management_api.call_api.permissions.CallLogPermission.has_permission", return_value=True)
    def test_missing_disconnection_reason_400(self, _perm):
        headers = {"HTTP_X_LIVEKIT_TOKEN": VALID_TOKEN}
        payload = {"call_task_id": str(self.call_task.id), "event_id": str(uuid.uuid4())}
        resp = self.client.post(ENDPOINT, data=payload, format="json", **headers)
        self.assertEqual(resp.status_code, 400)

    # ---------------- UNKNOWN FIELDS ----------------

    @patch("core.management_api.call_api.permissions.CallLogPermission.has_permission", return_value=True)
    def test_unknown_fields_ignored(self, _perm):
        headers = {"HTTP_X_LIVEKIT_TOKEN": VALID_TOKEN}
        payload = _payload(self.call_task.id, foo="bar", nested={"x": 1})

        with patch("core.management_api.call_api.views._record_usage_minutes") as usage, \
             patch("core.tasks.update_calltask_from_calllog.delay") as enqueue:
            resp = self.client.post(ENDPOINT, data=payload, format="json", **headers)

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(CallLog.objects.count(), 1)
        usage.assert_called_once()
        enqueue.assert_called_once()

    # ---------------- RACE / IntegrityError path ----------------

    @patch("core.management_api.call_api.permissions.CallLogPermission.has_permission", return_value=True)
    def test_race_on_event_id_unique_conflict_returns_existing(self, _perm):
        headers = {"HTTP_X_LIVEKIT_TOKEN": VALID_TOKEN}
        eid = str(uuid.uuid4())

        # Pre-create a CallLog with event_id to simulate the "other worker" winning the race
        CallLog.objects.create(
            call_task_id=self.call_task.id,
            agent=self.agent,
            lead=self.lead,
            from_number="+491234",
            to_number=self.call_task.phone,
            direction="outbound",
            duration=60,
            disconnection_reason="user_hangup",
            event_id=eid,
        )

        payload = _payload(self.call_task.id, event_id=eid)

        with patch("core.management_api.call_api.views._record_usage_minutes") as usage, \
             patch("core.tasks.update_calltask_from_calllog.delay") as enqueue:
            resp = self.client.post(ENDPOINT, data=payload, format="json", **headers)

        # Should return existing (200), no new row
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(CallLog.objects.count(), 1)
        # usage NOT called on duplicate
        usage.assert_not_called()
        # re-enqueue allowed since task not terminal
        enqueue.assert_called_once()

    # ---------------- LIST sanity ----------------

    def test_log_shows_in_list_after_post(self):
        self.client.force_authenticate(user=self.staff)
        payload = _payload(self.call_task.id)
        payload.pop("event_id", None)
        self.client.post(ENDPOINT, data=payload, format="json")

        # sanity check the list endpoint includes it
        list_resp = self.client.get("/api/calls/call-logs/")
        self.assertEqual(list_resp.status_code, 200)
        # DRF pagination may return {"results":[...]} or a full list
        data = list_resp.json()
        rows = data.get("results", data)
        self.assertTrue(any(str(r.get("call_task_id")) == str(self.call_task.id) for r in rows))


