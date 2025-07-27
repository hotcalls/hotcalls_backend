import asyncio
import os
import json
import uuid
from dotenv import load_dotenv
from livekit import api 
from livekit.protocol.sip import CreateSIPParticipantRequest

# Load environment variables from .env file
load_dotenv()

async def make_outbound_call(
    sip_trunk_id: str, 
    agent_config: dict,
    lead_data: dict,
    from_number: str,
    campaign_id: str,
    call_reason: str = None
):
    """
    Make an outbound call with comprehensive agent and lead configuration
    
    Args:
        sip_trunk_id (str): SIP trunk identifier
        agent_config (dict): Agent configuration including all agent fields
        lead_data (dict): Lead information including all lead fields
        from_number (str): Caller ID number
        campaign_id (str): Campaign identifier
        call_reason (str): Optional reason for the call (can be None)
    
    Returns:
        dict: Call details including room_name, participant_id, dispatch_id
    """
    # Configure LiveKit API with environment variables
    livekit_api = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET")
    )

    # Generate unique room name for this call
    room_name = f"outbound-call-{uuid.uuid4().hex[:8]}"
    
    # Prepare comprehensive metadata for the agent
    # 1) Pflichtfeld customer_name
    customer_name = f"{lead_data.get('name', '').strip()} {lead_data.get('surname', '').strip()}".strip()

    # 2) Optionaler call_reason
    # Template-Ersetzung direkt hier
    greeting_template = agent_config.get('greeting_outbound', 'Hello {name} {surname}, how are you?')
    custom_greeting = greeting_template.format(
        name=lead_data.get("name", ""),
        surname=lead_data.get("surname", "")
    )
    
    # Backward-Kompatibilität: agent_name als Alias für name hinzufügen
    agent_config["agent_name"] = agent_config.get("name", "")
    
    metadata = {
        # Neue flache Outbound-Keys
        "phone_number": lead_data.get("phone"),
        "customer_name": customer_name,
        "call_reason": call_reason,        # kann None sein
        "custom_greeting": custom_greeting,  # Bereits ersetzter Text
        "name": lead_data.get("name", ""),
        "surname": lead_data.get("surname", ""), 
        "email": lead_data.get("email", ""),

        # Bestehende Schlüssel für rückwärts­kompatible Workflows
        "agent_config": agent_config,
        "lead_data": lead_data,
        "from_number": from_number,
        "campaign_id": campaign_id
    }

    if not customer_name:
        # Kein Outbound-Kontext → Inbound-Kompatibilität
        metadata.pop("customer_name", None)
    else:
        # Grund­legende Sanitization
        metadata["customer_name"] = customer_name.replace('"', '').replace("'", "")
    
    try:
        # Step 1: Dispatch the agent to the room first
        print(f"Dispatching {agent_config['name']} to room for call to {lead_data['phone']}...")
        dispatch = await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=agent_config['name'],
                room=room_name,
                metadata=json.dumps(metadata)
            )
        )
        print(f"Agent dispatched: {dispatch.id}")
        
        # Step 2: Create the SIP participant (make the call)
        print(f"Creating outbound call to {lead_data['phone']}...")
        request = CreateSIPParticipantRequest(
            sip_trunk_id=sip_trunk_id,
            sip_call_to=lead_data['phone'],
            room_name=room_name,
            participant_identity=f"lead_{lead_data['name']}_{lead_data['surname']}",
            participant_name=f"{lead_data['name']} {lead_data['surname']}",
            # Optional: Add from_number handling if needed
        )
        
        participant = await livekit_api.sip.create_sip_participant(request)
        print(f"Call connected: {participant}")
        print(f"Room: {room_name}")
        
        return {
            "success": True,
            "room_name": room_name,
            "participant_id": participant.participant_id,
            "dispatch_id": dispatch.id,
            "sip_call_id": participant.sip_call_id,
            "to_number": lead_data['phone'],
            "agent_name": agent_config['name'],
            "campaign_id": campaign_id
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return {
            "success": False,
            "error": str(e),
            "to_number": lead_data['phone'],
            "agent_name": agent_config['name'],
            "campaign_id": campaign_id
        }
    finally:
        await livekit_api.aclose()

def make_outbound_call_sync(
    sip_trunk_id: str, 
    agent_config: dict,
    lead_data: dict,
    from_number: str,
    campaign_id: str,
    call_reason: str = None
):
    """
    Synchroner Wrapper für make_outbound_call - kann von normalem Python Code aufgerufen werden
    
    **WICHTIG: NICHT ASYNC! Kann von Django synchronen Views verwendet werden!**
    
    Args:
        sip_trunk_id (str): SIP trunk identifier
        agent_config (dict): Agent configuration
        lead_data (dict): Lead information
        from_number (str): Caller ID number
        campaign_id (str): Campaign identifier
        call_reason (str): Optional reason for the call (can be None)
    
    Returns:
        dict: Call details including room_name, participant_id, dispatch_id
    """
    return asyncio.run(make_outbound_call(
        sip_trunk_id=sip_trunk_id,
        agent_config=agent_config,
        lead_data=lead_data,
        from_number=from_number,
        campaign_id=campaign_id,
        call_reason=call_reason
    )) 