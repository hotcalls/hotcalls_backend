from __future__ import annotations

import os
import json
import uuid
import datetime
import contextlib
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from livekit import api
from livekit.protocol.sip import CreateSIPParticipantRequest


load_dotenv()


async def _make_call_async(
    sip_trunk_id: str,
    agent_config: Dict[str, Any],
    lead_data: Dict[str, Any],
    from_number: str,
    *,
    call_task_id: Optional[str] = None,
    room_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Place an outbound call via LiveKit and return identifiers.

    Notes:
    - Adds a stable callee_identity into job metadata for the agent to wait on
    - Does not rely on experimental wait_until_answered flags
    - Returns a deterministic dict. Never raises; errors are returned.
    """
    from core.utils.calltask_utils import preflight_check_agent_token_async

    livekit_api = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
    )

    room_name = room_name or f"outbound-call-{uuid.uuid4().hex[:8]}"
    agent_name = os.getenv("LIVEKIT_AGENT_NAME", "hotcalls_agent")
    # Backward-compatibility: expose agent_name in agent_config as alias
    agent_config["agent_name"] = agent_name

    callee_phone = (lead_data.get("phone") or "").strip()
    callee_identity = f"phone_{callee_phone.replace('+', '')}"

    # --- Job metadata sent to the agent process ---
    hotcalls_metadata = {
        # Keep metadata compatible with the previous implementation
        "agent": "hotcalls_agent",
        "call_type": "outbound",
        "to_number": callee_phone,
        "from_number": from_number,
        "call_task_id": call_task_id or lead_data.get("call_task_id", ""),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sip_provider": "jambonz",
        "agent_config": {
            "voice_external_id": agent_config.get("voice_external_id", ""),
            "name": agent_config.get("name", ""),
            "language": agent_config.get("language", "de"),
            "workspace_name": agent_config.get("workspace_name", ""),
            "character": agent_config.get("character", ""),
            "greeting_inbound": agent_config.get("greeting_inbound", ""),
            "greeting_outbound": agent_config.get("greeting_outbound", ""),
        },
        "lead_data": {
            "id": lead_data.get("id", ""),
            "name": (lead_data.get("name", "") or "").replace('"', "").replace("'", ""),
            "surname": (lead_data.get("surname", "") or "").replace('"', "").replace("'", ""),
            "phone": callee_phone,
            "email": lead_data.get("email", ""),
        },
    }

    try:
        # 0) Preflight agent token
        token_check = await preflight_check_agent_token_async(agent_name)
        if not token_check.get("valid"):
            return {
                "success": False,
                "error": f"Agent {agent_name}: {token_check.get('reason')}",
                "to_number": callee_phone,
                "agent_name": agent_name,
                "abort_reason": "token_missing",
            }

        # 1) Dispatch agent to room with metadata
        try:
            dispatch = await livekit_api.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=agent_name,
                    room=room_name,
                    metadata=json.dumps(hotcalls_metadata, ensure_ascii=False),
                )
            )
        except Exception as dispatch_error:
            return {
                "success": False,
                "error": f"Agent dispatch failed: {str(dispatch_error)}",
                "to_number": callee_phone,
                "agent_name": agent_name,
                "abort_reason": "dispatch_failed",
            }

        # 2) Create SIP participant (no experimental args)
        participant_identity = callee_identity
        participant_name = f"Outbound Call to {callee_phone}"

        request = CreateSIPParticipantRequest(
            sip_trunk_id=sip_trunk_id,
            sip_call_to=callee_phone,
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name=participant_name,
        )

        # The client supports a timeout param when invoking the API call itself
        # Match previous behavior: no explicit timeout argument passed here
        participant = await livekit_api.sip.create_sip_participant(request)

        return {
            "success": True,
            "room_name": room_name,
            "participant_id": participant.participant_id,
            "dispatch_id": dispatch.id,
            "sip_call_id": participant.sip_call_id,
            "to_number": callee_phone,
            "agent_name": agent_name,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "to_number": callee_phone,
            "agent_name": agent_name,
            "abort_reason": "exception",
        }
    finally:
        with contextlib.suppress(Exception):
            await livekit_api.aclose()




