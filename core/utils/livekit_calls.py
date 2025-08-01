import os
import json
import uuid
import datetime
from dotenv import load_dotenv
from livekit import api 
from livekit.protocol.sip import CreateSIPParticipantRequest

# Load environment variables from .env file
load_dotenv()

# All wrapper functions removed - now only _make_call_async remains for pure call execution

async def _make_call_async(
    sip_trunk_id: str, 
    agent_config: dict,
    lead_data: dict,
    from_number: str,
    campaign_id: str,
    call_reason: str = None
):
    """
    Internal async function to make the actual LiveKit call
    """
    # Configure LiveKit API with environment variables
    livekit_api = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET")
    )

    # Generate unique room name for this call
    room_name = f"outbound-call-{uuid.uuid4().hex[:8]}"
    
    
    # Backward-Kompatibilität: agent_name als Alias für name hinzufügen
    agent_config["agent_name"] = os.getenv("LIVEKIT_AGENT_NAME", "hotcalls_agent")
    
    # === AGENT JOB METADATA (EXAKT nach Agent Integration Guide) ===
    hotcalls_metadata = {
        "agent": "hotcalls_agent",
        "call_type": "outbound", 
        "to_number": lead_data.get("phone", ""),
        "from_number": from_number,
        "correlation_id": f"hotcalls-{uuid.uuid4().hex[:8]}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sip_provider": "jambonz",
        
        "agent_config": {
            "voice_external_id": agent_config.get('voice_external_id', ''),
            "name": agent_config.get('name', ''),
            "language": agent_config.get('language', 'de'),
            "workspace_name": agent_config.get('workspace_name', ''),
            "character": agent_config.get('character', ''),
            "greeting_inbound": agent_config.get('greeting_inbound', ''),
            "greeting_outbound": agent_config.get('greeting_outbound', '')
        },
        
        "lead_data": {
            "id": lead_data.get("id", ""),
            "name": lead_data.get("name", ""),
            "surname": lead_data.get("surname", ""),
            "phone": lead_data.get("phone", ""),
            "email": lead_data.get("email", "")
        }
    }


    # Sanitize lead names
    if lead_data.get("name"):
        hotcalls_metadata["lead_data"]["name"] = lead_data["name"].replace('"', '').replace("'", "")
    if lead_data.get("surname"):
        hotcalls_metadata["lead_data"]["surname"] = lead_data["surname"].replace('"', '').replace("'", "")
    
    try:
        # Step 1: Dispatch the agent to the room first
        agent_name = os.getenv("LIVEKIT_AGENT_NAME", "hotcalls_agent")
        print(f"Dispatching {agent_name} to room for call to {lead_data['phone']}...")
        
        dispatch = await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata=json.dumps(hotcalls_metadata, ensure_ascii=False)
            )
        )
        print(f"Agent dispatched: {dispatch.id}")
        
        # Step 2: Create the SIP participant (make the call)
        
        # Generate participant identity and name
        participant_identity = f"phone_{lead_data['phone'].replace('+', '')}"
        participant_name = f"Outbound Call to {lead_data['phone']}"
        
        request = CreateSIPParticipantRequest(
            sip_trunk_id=sip_trunk_id,
            sip_call_to=lead_data['phone'],
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name=participant_name
        )
        
        participant = await livekit_api.sip.create_sip_participant(request)
        
        return {
            "success": True,
            "room_name": room_name,
            "participant_id": participant.participant_id,
            "dispatch_id": dispatch.id,
            "sip_call_id": participant.sip_call_id,
            "to_number": lead_data['phone'],
            "agent_name": os.getenv("LIVEKIT_AGENT_NAME", "hotcalls_agent"),
            "campaign_id": campaign_id
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "to_number": lead_data['phone'],
            "agent_name": os.getenv("LIVEKIT_AGENT_NAME", "hotcalls_agent"),
            "campaign_id": campaign_id
        }
    finally:
        await livekit_api.aclose() 