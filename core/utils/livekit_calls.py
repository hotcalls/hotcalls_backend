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
    
    # Handle empty names in greeting
    if customer_name:
        custom_greeting = greeting_template.format(
            name=lead_data.get("name", ""),
            surname=lead_data.get("surname", "")
        )
    else:
        # No customer name, use generic greeting
        custom_greeting = agent_config.get('greeting_outbound', 'Hello, how are you?')
    
    # Backward-Kompatibilität: agent_name als Alias für name hinzufügen
    agent_config["agent_name"] = "hotcalls_agent"  # Use hotcalls_agent for external API compatibility
    
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
        print(f"Dispatching hotcalls_agent to room for call to {lead_data['phone']}...")
        dispatch = await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="hotcalls_agent",  # Use hotcalls_agent for external API compatibility
                room=room_name,
                metadata=json.dumps(metadata)
            )
        )
        print(f"Agent dispatched: {dispatch.id}")
        
        # Step 2: Create the SIP participant (make the call)
        print(f"Creating outbound call to {lead_data['phone']}...")
        
        # Generate participant identity and name
        if customer_name:
            participant_identity = f"lead_{lead_data['name']}_{lead_data['surname']}"
            participant_name = f"{lead_data['name']} {lead_data['surname']}"
        else:
            # No lead info, use phone-based identity
            participant_identity = f"phone_{lead_data['phone'].replace('+', '')}"
            participant_name = f"Outbound Call to {lead_data['phone']}"
        
        request = CreateSIPParticipantRequest(
            sip_trunk_id=sip_trunk_id,
            sip_call_to=lead_data['phone'],
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name=participant_name,
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
            "agent_name": "hotcalls_agent",  # Return hotcalls_agent for external API compatibility
            "campaign_id": campaign_id
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return {
            "success": False,
            "error": str(e),
            "to_number": lead_data['phone'],
            "agent_name": "agent_4",  # Always return agent_4 for outbound calls
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
        agent_config = {
            'name': agent.name,
            'voice_id': agent.voice.voice_external_id if agent.voice else None,
            'language': agent.language,
            'prompt': agent.prompt,
            'greeting_outbound': agent.greeting_outbound,
            'greeting_inbound': agent.greeting_inbound,
            'character': agent.character,
            'config_id': agent.config_id,
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
        workspace = call_task.workspace
        sip_trunk_id = workspace.sip_trunk_id if hasattr(workspace, 'sip_trunk_id') else os.getenv('TRUNK_ID')
        
        # Get first phone number from agent's phone_numbers or use workspace/default
        agent_phone = None
        if agent.phone_numbers.exists():
            agent_phone = agent.phone_numbers.first().phonenumber
        
        from_number = agent_phone or (workspace.phone_number if hasattr(workspace, 'phone_number') else os.getenv('DEFAULT_FROM_NUMBER'))
        
        # Use workspace id as campaign_id
        campaign_id = str(workspace.id)
        
        # Make the call
        result = make_outbound_call_sync(
            sip_trunk_id=sip_trunk_id,
            agent_config=agent_config,
            lead_data=lead_data,
            from_number=from_number,
            campaign_id=campaign_id,
            call_reason=call_reason
        )
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'call_task_id': str(call_task.id)
        } 