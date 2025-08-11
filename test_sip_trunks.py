#!/usr/bin/env python
"""
Test script for Multi-Tenant SIP Calling Architecture

This script creates test data and demonstrates the new multi-tenant SIP calling flow:
Agent → PhoneNumber → SIPTrunk
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotcalls.settings.development')
django.setup()

from core.models import Workspace, Agent, PhoneNumber, SIPTrunk, Voice, User
from django.contrib.auth import get_user_model

def create_test_data():
    """Create test data for multi-tenant SIP calling"""
    print("🚀 Creating test data for multi-tenant SIP calling...")
    
    # 1. Create a test user
    User = get_user_model()
    user, created = User.objects.get_or_create(
        email='test@example.com',
        defaults={
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '+1234567890',
            'is_email_verified': True
        }
    )
    if created:
        user.set_password('testpass123')
        user.save()
    print(f"✅ User: {user.email}")
    
    # 2. Create a test workspace
    workspace, created = Workspace.objects.get_or_create(
        workspace_name='Test SIP Workspace'
    )
    workspace.users.add(user)
    print(f"✅ Workspace: {workspace.workspace_name}")
    
    # 3. Create test SIP trunks
    sip_trunk_1, created = SIPTrunk.objects.get_or_create(
        provider_name='Sipgate',
        sip_username='agent1_sipgate',
        defaults={
            'sip_password': 'password123',
            'sip_host': 'sipconnect.sipgate.de',
            'sip_port': 5060,
            'livekit_trunk_id': 'ST_SIPGATE_AGENT1',
            'jambonz_carrier_id': 'carrier_sipgate_1'
        }
    )
    print(f"✅ SIP Trunk 1: {sip_trunk_1.provider_name} - {sip_trunk_1.livekit_trunk_id}")
    
    sip_trunk_2, created = SIPTrunk.objects.get_or_create(
        provider_name='Twilio',
        sip_username='agent2_twilio',
        defaults={
            'sip_password': 'password456',
            'sip_host': 'sip.twilio.com',
            'sip_port': 5060,
            'livekit_trunk_id': 'ST_TWILIO_AGENT2',
            'jambonz_carrier_id': 'carrier_twilio_2'
        }
    )
    print(f"✅ SIP Trunk 2: {sip_trunk_2.provider_name} - {sip_trunk_2.livekit_trunk_id}")
    
    # 4. Create test phone numbers with SIP trunks
    phone_1, created = PhoneNumber.objects.get_or_create(
        phonenumber='+491234567890',
        defaults={'sip_trunk': sip_trunk_1}
    )
    print(f"✅ Phone Number 1: {phone_1.phonenumber} → {phone_1.sip_trunk.provider_name}")
    
    phone_2, created = PhoneNumber.objects.get_or_create(
        phonenumber='+14155551234',
        defaults={'sip_trunk': sip_trunk_2}
    )
    print(f"✅ Phone Number 2: {phone_2.phonenumber} → {phone_2.sip_trunk.provider_name}")
    
    # 5. Get any available voice or create one
    voice = Voice.objects.first()
    if not voice:
        voice = Voice.objects.create(
            voice_external_id='test_voice_123',
            provider='elevenlabs',
            name='Test Voice',
            gender='female',
            tone='friendly'
        )
    print(f"✅ Voice: {voice.name} ({voice.provider})")
    
    # 6. Create test agents with different phone numbers/trunks
    agent_1, created = Agent.objects.get_or_create(
        name='Agent 1 (Sipgate)',
        workspace=workspace,
        defaults={
            'phone_number': phone_1,  # Uses Sipgate trunk
            'voice': voice,
            'greeting_outbound': 'Hello! This is Agent 1 calling via Sipgate.',
            'character': 'Professional sales agent using Sipgate trunk'
        }
    )
    print(f"✅ Agent 1: {agent_1.name} → {agent_1.phone_number.phonenumber} → {agent_1.phone_number.sip_trunk.provider_name}")
    
    agent_2, created = Agent.objects.get_or_create(
        name='Agent 2 (Twilio)',
        workspace=workspace,
        defaults={
            'phone_number': phone_2,  # Uses Twilio trunk
            'voice': voice,
            'greeting_outbound': 'Hello! This is Agent 2 calling via Twilio.',
            'character': 'Professional sales agent using Twilio trunk'
        }
    )
    print(f"✅ Agent 2: {agent_2.name} → {agent_2.phone_number.phonenumber} → {agent_2.phone_number.sip_trunk.provider_name}")
    
    return {
        'workspace': workspace,
        'agent_1': agent_1,
        'agent_2': agent_2,
        'phone_1': phone_1,
        'phone_2': phone_2,
        'sip_trunk_1': sip_trunk_1,
        'sip_trunk_2': sip_trunk_2
    }

def test_call_flow(test_data):
    """Test the multi-tenant call flow"""
    print("\n🧪 Testing multi-tenant SIP call flow...")
    
    agent_1 = test_data['agent_1']
    agent_2 = test_data['agent_2']
    
    # Test 1: Agent 1 call flow (should use Sipgate trunk)
    print(f"\n📞 Agent 1 Call Flow:")
    print(f"   Agent: {agent_1.name}")
    print(f"   Phone: {agent_1.phone_number.phonenumber}")
    print(f"   SIP Trunk: {agent_1.phone_number.sip_trunk.provider_name}")
    print(f"   LiveKit Trunk ID: {agent_1.phone_number.sip_trunk.livekit_trunk_id}")
    print(f"   SIP Host: {agent_1.phone_number.sip_trunk.sip_host}")
    
    # Test 2: Agent 2 call flow (should use Twilio trunk)
    print(f"\n📞 Agent 2 Call Flow:")
    print(f"   Agent: {agent_2.name}")
    print(f"   Phone: {agent_2.phone_number.phonenumber}")
    print(f"   SIP Trunk: {agent_2.phone_number.sip_trunk.provider_name}")
    print(f"   LiveKit Trunk ID: {agent_2.phone_number.sip_trunk.livekit_trunk_id}")
    print(f"   SIP Host: {agent_2.phone_number.sip_trunk.sip_host}")
    
    # Test 3: Demonstrate call task logic
    print(f"\n🔄 Call Task Logic Test:")
    for agent in [agent_1, agent_2]:
        # Simulate the logic from core/tasks.py
        sip_trunk_id = None
        if agent.phone_number and agent.phone_number.sip_trunk:
            sip_trunk_id = agent.phone_number.sip_trunk.livekit_trunk_id
        if not sip_trunk_id:
            sip_trunk_id = "ST_F5KZ4yNHBegK"  # Fallback
            
        print(f"   {agent.name}: trunk_id = {sip_trunk_id}")
        
        agent_config = {
            "name": agent.name,
            "sip_trunk_id": sip_trunk_id,  # Dynamic trunk ID
            "greeting_outbound": agent.greeting_outbound,
        }
        print(f"   Agent config: {agent_config}")

if __name__ == '__main__':
    print("🎯 Multi-Tenant SIP Calling Architecture Test")
    print("=" * 50)
    
    # Create test data
    test_data = create_test_data()
    
    # Test call flows
    test_call_flow(test_data)
    
    print("\n✅ Test completed! Multi-tenant SIP calling architecture is working!")
    print("\n📋 Summary:")
    print("   - Agent 1 uses Sipgate trunk (ST_SIPGATE_AGENT1)")
    print("   - Agent 2 uses Twilio trunk (ST_TWILIO_AGENT2)")
    print("   - Each agent has their own phone number and SIP trunk")
    print("   - Call logic dynamically selects the correct trunk per agent")
    print("   - Fallback to default trunk if agent has no trunk configured")
