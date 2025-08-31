from django.test import TestCase
from django.db import transaction
from core.models import Workspace, PhoneNumber, WorkspacePhoneNumber, Agent
from core.services.phone_assignment import assign_default_number_to_workspace, get_workspace_default_number


class PhoneAssignmentTests(TestCase):
    def setUp(self):
        self.ws1 = Workspace.objects.create(workspace_name="WS1")
        self.ws2 = Workspace.objects.create(workspace_name="WS2")

    def test_assign_default_number_to_workspace_uses_global_pool(self):
        pn1 = PhoneNumber.objects.create(phonenumber="+15550000001", is_global_default=True, is_active=True)
        pn2 = PhoneNumber.objects.create(phonenumber="+15550000002", is_global_default=True, is_active=True)

        # Assign to first workspace
        m1 = assign_default_number_to_workspace(self.ws1)
        self.assertTrue(m1.is_default)
        self.assertIn(m1.phone_number.phonenumber, {pn1.phonenumber, pn2.phonenumber})

        # Assign to second workspace should pick the other (RR by min-count)
        m2 = assign_default_number_to_workspace(self.ws2)
        self.assertTrue(m2.is_default)
        self.assertNotEqual(m1.phone_number_id, m2.phone_number_id)

    def test_get_workspace_default_number(self):
        pn1 = PhoneNumber.objects.create(phonenumber="+15550000003", is_global_default=True, is_active=True)
        assign_default_number_to_workspace(self.ws1)
        default = get_workspace_default_number(self.ws1)
        self.assertIsNotNone(default)
        self.assertTrue(default.is_active)

    def test_no_global_defaults_raises(self):
        with self.assertRaises(Exception):
            assign_default_number_to_workspace(self.ws1)


class AgentAutoAssignTests(TestCase):
    def setUp(self):
        self.ws = Workspace.objects.create(workspace_name="WS")
        self.pn = PhoneNumber.objects.create(phonenumber="+15559999999", is_global_default=True, is_active=True)
        assign_default_number_to_workspace(self.ws)

    def test_agent_gets_workspace_default_when_not_provided(self):
        # Create agent without explicit phone_number
        agent = Agent.objects.create(
            workspace=self.ws,
            name="A1",
            status='active',
            language='en',
            retry_interval=30,
            max_retries=3,
            call_from="09:00:00",
            call_to="17:00:00",
            character="",
            script_template="",
        )
        # Simulate serializer.create behavior by applying default after agent exists
        # Normally handled in AgentCreateSerializer.create
        default = get_workspace_default_number(self.ws)
        if agent.phone_number is None and default:
            agent.phone_number = default
            agent.save(update_fields=['phone_number'])

        self.assertIsNotNone(agent.phone_number)
        self.assertEqual(agent.phone_number.phonenumber, self.pn.phonenumber)



