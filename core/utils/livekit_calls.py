import asyncio
import os
import json
import uuid
import datetime
from dotenv import load_dotenv
from livekit import api 
from livekit.protocol.sip import CreateSIPParticipantRequest

# Load environment variables from .env file
load_dotenv()

def initiate_call_from_task(call_task):
    """
    Initiate an outbound call from a CallTask object
    
    Args:
        call_task: CallTask model instance
    
    Returns:
        dict: Call result with success status and details
    """
    try:
        # Get agent configuration
        agent = call_task.agent
        workspace = call_task.workspace
        agent_config = {
            'name': agent.name,
            'voice_external_id': agent.voice.voice_external_id if agent.voice else None,
            'language': agent.language,
            'prompt': agent.prompt,
            'greeting_outbound': agent.greeting_outbound,
            'greeting_inbound': agent.greeting_inbound,
            'character': agent.character,
            'config_id': agent.config_id,
            'workspace_name': workspace.workspace_name,
        }
        
        # Get lead data or create test data
        if call_task.lead:
            # Real call with lead
            lead = call_task.lead
            lead_data = {
                'id': str(lead.id),
                'name': lead.name,
                'surname': lead.surname,
                'email': lead.email,
                'phone': lead.phone,
                'company': lead.company,
                'address': lead.address,
                'city': lead.city,
                'state': lead.state,
                'zip_code': lead.zip_code,
                'country': lead.country,
                'notes': lead.notes,
                'metadata': lead.metadata,
            }
            call_reason = None
        else:
            # Test call without lead
            lead_data = {
                'id': str(call_task.id),
                'name': 'Test',
                'surname': 'Call',
                'email': 'test@example.com',
                'phone': call_task.phone,
                'company': 'Test Company',
                'address': '',
                'city': '',
                'state': '',
                'zip_code': '',
                'country': '',
                'notes': 'Test call',
                'metadata': {'test_call': True, 'call_task_id': str(call_task.id)},
            }
            call_reason = "Test call - triggered manually"
        
        # Get workspace for SIP trunk and campaign info
        sip_trunk_id = workspace.sip_trunk_id if hasattr(workspace, 'sip_trunk_id') else os.getenv('TRUNK_ID')
        
        # Get first phone number from agent's phone_numbers or use workspace/default
        agent_phone = None
        if agent.phone_numbers.exists():
            agent_phone = agent.phone_numbers.first().phonenumber
        
        from_number = agent_phone or (workspace.phone_number if hasattr(workspace, 'phone_number') else os.getenv('DEFAULT_FROM_NUMBER'))
        
        # Use workspace id as campaign_id
        campaign_id = str(workspace.id)
        
        # === INTEGRATED LIVEKIT CALL LOGIC ===
        return asyncio.run(_make_call_async(
            sip_trunk_id=sip_trunk_id,
            agent_config=agent_config,
            lead_data=lead_data,
            from_number=from_number,
            campaign_id=campaign_id,
            call_reason=call_reason
        ))
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'call_task_id': str(call_task.id)
        }

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