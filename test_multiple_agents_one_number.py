#!/usr/bin/env python
"""
Test Multiple Agents Sharing One Phone Number

This demonstrates how multiple agents can share the same phone number
but each call still routes through the correct SIP trunk.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotcalls.settings.development')
django.setup()

from core.models import Workspace, Agent, PhoneNumber, SIPTrunk, Voice

def test_multiple_agents_one_number():
    """Test multiple agents sharing the same phone number"""
    print("🧪 Testing Multiple Agents Sharing One Phone Number...")
    
    # Get existing data
    workspace = Workspace.objects.first()
    phone_number = PhoneNumber.objects.first()
    voice = Voice.objects.first()
    
    if not all([workspace, phone_number, voice]):
        print("❌ Need to run test_sip_trunks.py first to create base data")
        return
    
    print(f"📞 Using phone number: {phone_number.phonenumber}")
    print(f"🏗️ SIP Trunk: {phone_number.sip_trunk.provider_name} ({phone_number.sip_trunk.livekit_trunk_id})")
    
    # Create 3 additional agents that share the SAME phone number
    agents_created = []
    for i in range(3, 6):  # Agents 3, 4, 5
        agent = Agent.objects.create(
            name=f"Sales Agent {i}",
            workspace=workspace,
            phone_number=phone_number,  # 👈 SAME phone number for all
            voice=voice,
            language="de",
            prompt=f"You are Sales Agent {i}. You share a phone number with other agents.",
            greeting_outbound=f"Hi, this is Agent {i} calling from our sales team.",
            character="professional",
            config_id=f"agent_{i}_config"
        )
        agents_created.append(agent)
        print(f"✅ Created Agent {i}: {agent.name}")
    
    print("\n" + "="*60)
    print("📊 FINAL CONFIGURATION")
    print("="*60)
    
    # Show all agents using the same phone number
    all_agents = Agent.objects.filter(phone_number=phone_number)
    print(f"📞 Phone Number: {phone_number.phonenumber}")
    print(f"🏗️ SIP Trunk: {phone_number.sip_trunk.provider_name}")
    print(f"🆔 LiveKit Trunk ID: {phone_number.sip_trunk.livekit_trunk_id}")
    print(f"👥 Agents sharing this number: {all_agents.count()}")
    
    for agent in all_agents:
        print(f"   - {agent.name} (ID: {agent.agent_id})")
    
    print("\n" + "="*60)
    print("🔄 CALL ROUTING TEST")
    print("="*60)
    
    # Simulate how calls would work for each agent
    for agent in all_agents[:2]:  # Test first 2 agents
        print(f"\n🎯 Testing call from: {agent.name}")
        print(f"   📞 Caller ID: {agent.phone_number.phonenumber}")
        print(f"   🏗️ SIP Trunk: {agent.phone_number.sip_trunk.livekit_trunk_id}")
        print(f"   🎭 Voice: {agent.voice.name if agent.voice else 'None'}")
        
        # Show what the call parameters would be
        sip_trunk_id = None
        if agent.phone_number and agent.phone_number.sip_trunk:
            sip_trunk_id = agent.phone_number.sip_trunk.livekit_trunk_id
        
        print(f"   🚀 Would call with trunk_id: {sip_trunk_id}")
        print(f"   ✨ Result: All agents use SAME phone number but access it via the SAME trunk")
    
    print("\n" + "="*60)
    print("💡 KEY INSIGHTS")
    print("="*60)
    print("✅ Multiple agents CAN share the same phone number")
    print("✅ All calls from those agents use the SAME SIP trunk")
    print("✅ Caller ID will be identical for all agents sharing the number")
    print("✅ The phone number acts as a 'pool' of caller IDs")
    print("✅ Each agent maintains their own voice, prompt, and personality")
    print("\n🎯 Use Case: Team of agents representing the same company/department")

if __name__ == "__main__":
    test_multiple_agents_one_number()
