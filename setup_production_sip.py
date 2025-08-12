#!/usr/bin/env python
"""
Production SIP Setup Script

Use this script to add real SIP trunks and phone numbers to your system.
Replace the example values with your actual provider credentials.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotcalls.settings.development')
django.setup()

from core.models import Workspace, Agent, PhoneNumber, SIPTrunk, Voice

def setup_production_sip():
    """Setup production SIP trunks and phone numbers"""
    print("🚀 Setting up Production SIP Configuration...")
    
    # Get your workspace
    workspace = Workspace.objects.first()
    if not workspace:
        print("❌ No workspace found. Create a workspace first.")
        return
    
    print(f"📋 Using workspace: {workspace.workspace_name}")
    
    # === SIPGATE GERMANY SETUP ===
    print("\n🇩🇪 Setting up Sipgate Germany...")
    
    # 1. Create Sipgate SIP Trunk
    sipgate_trunk = SIPTrunk.objects.create(
        provider_name="Sipgate",
        sip_username="YOUR_SIPGATE_USERNAME",  # Replace with: agent1@company.sipgate.de
        sip_password="YOUR_SIPGATE_PASSWORD",  # Replace with your Sipgate password
        sip_host="sipconnect.sipgate.de",
        sip_port=5060,
        jambonz_carrier_id="",  # Will be set when Jambonz is configured
        livekit_trunk_id="ST_SIPGATE_PRODUCTION",  # Your LiveKit trunk ID
        is_active=True
    )
    
    # 2. Create German Phone Number
    german_number = PhoneNumber.objects.create(
        phonenumber="+491234567890",  # Replace with your actual Sipgate number
        sip_trunk=sipgate_trunk,
        is_active=True
    )
    
    print(f"✅ Created Sipgate trunk: {sipgate_trunk.livekit_trunk_id}")
    print(f"✅ Created German number: {german_number.phonenumber}")
    
    # === TWILIO US SETUP ===
    print("\n🇺🇸 Setting up Twilio US...")
    
    # 3. Create Twilio SIP Trunk
    twilio_trunk = SIPTrunk.objects.create(
        provider_name="Twilio",
        sip_username="YOUR_TWILIO_USERNAME",   # Replace with your Twilio SIP username
        sip_password="YOUR_TWILIO_PASSWORD",   # Replace with your Twilio auth token
        sip_host="sip.twilio.com",
        sip_port=5060,
        jambonz_carrier_id="",
        livekit_trunk_id="ST_TWILIO_PRODUCTION",  # Your LiveKit trunk ID
        is_active=True
    )
    
    # 4. Create US Phone Number
    us_number = PhoneNumber.objects.create(
        phonenumber="+14155551234",  # Replace with your actual Twilio number
        sip_trunk=twilio_trunk,
        is_active=True
    )
    
    print(f"✅ Created Twilio trunk: {twilio_trunk.livekit_trunk_id}")
    print(f"✅ Created US number: {us_number.phonenumber}")
    
    # === ASSIGN TO AGENTS ===
    print("\n🤖 Assigning numbers to agents...")
    
    # Get existing agents or create new ones
    german_agent = Agent.objects.filter(workspace=workspace).first()
    if german_agent:
        german_agent.phone_number = german_number
        german_agent.save()
        print(f"✅ Assigned German number to: {german_agent.name}")
    
    # Show final configuration
    print("\n" + "="*60)
    print("📊 PRODUCTION SIP CONFIGURATION")
    print("="*60)
    
    for trunk in SIPTrunk.objects.all():
        phone = trunk.phone_number
        agents = phone.agents.all() if phone else []
        
        print(f"\n🏗️ {trunk.provider_name} Trunk:")
        print(f"   📞 Phone: {phone.phonenumber if phone else 'None'}")
        print(f"   🆔 LiveKit ID: {trunk.livekit_trunk_id}")
        print(f"   🌐 SIP Host: {trunk.sip_host}")
        print(f"   👥 Agents: {agents.count()}")
        for agent in agents:
            print(f"      - {agent.name}")
    
    print("\n" + "="*60)
    print("📋 NEXT STEPS")
    print("="*60)
    print("1. 🔐 Replace placeholder credentials with real ones")
    print("2. 🏗️ Configure LiveKit trunk IDs in LiveKit dashboard")
    print("3. 🌐 Set up Jambonz carriers (optional, for advanced routing)")
    print("4. 📞 Test calls with real phone numbers")
    print("5. 🚀 Deploy to production!")

if __name__ == "__main__":
    print("⚠️  PRODUCTION SETUP - Review credentials before running!")
    print("📝 Edit this script and replace placeholder values with real credentials")
    print("🔐 Make sure to keep credentials secure!")
    
    response = input("\nProceed with setup? (y/N): ")
    if response.lower() in ['y', 'yes']:
        setup_production_sip()
    else:
        print("Setup cancelled. Edit the script with your real credentials first.")
