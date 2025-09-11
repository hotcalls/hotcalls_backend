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


def _fetch_knowledge_content(agent_id: str, doc_ids: list) -> str:
    """
    Fetch full knowledge document content using the actual knowledge API function logic.
    
    Args:
        agent_id: Agent UUID  
        doc_ids: List of document IDs (currently only supports single doc)
        
    Returns:
        Combined full text content of all documents
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not doc_ids:
        logger.info(f"KNOWLEDGE FETCH ABORTED: no doc_ids")
        return ""
    
    logger.info(f"KNOWLEDGE FETCH STARTED")
    
    try:
        from core.management_api.knowledge_api.views import _get_agent_or_404, AzureMediaStorage
        
        agent = _get_agent_or_404(agent_id)
        storage = AzureMediaStorage()

        if agent.kb_pdf:
            # Use exact same logic as AgentKnowledgeDocumentPresignByIdView
            current_name = os.path.basename(agent.kb_pdf.name)
            base_no_ext = os.path.splitext(current_name)[0]
            path = agent.kb_pdf.name
            dir_path = os.path.dirname(path)
            txt_path = f"{dir_path}/{base_no_ext}.txt"
            
            if storage.exists(txt_path):
                with storage.open(txt_path, "rb") as fh:
                    content = fh.read().decode("utf-8")
                    logger.info(f"KNOWLEDGE FETCH COMPLETE")
                    return content.strip()
            else:
                logger.warning(f"KNOWLEDGE FETCH FAILED: no txt file at {txt_path}")
        else:
            logger.warning(f"KNOWLEDGE FETCH FAILED: agent {agent_id} has no kb_pdf")

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to fetch knowledge content for agent {agent_id}: {e}")
        
    return ""


async def _make_call_async(
    sip_trunk_id: str,
    agent_config: Dict[str, Any],
    lead_data: Dict[str, Any],
    from_number: str,
    *,
    call_task_id: Optional[str] = None,
    room_name: Optional[str] = None,
    answer_timeout_s: Optional[float] = None,
    knowledge_content,
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
    agent_name = os.getenv("LIVEKIT_AGENT_NAME")
    # Expose agent_name in agent_config as alias (no fallback value)
    agent_config["agent_name"] = agent_name

    callee_phone = (lead_data.get("phone") or "").strip()
    callee_identity = f"phone_{callee_phone.replace('+', '')}"

    # DEBUG: Log what we received from tasks.py
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"📥 DIALER RECEIVED FROM TASKS - script_template: {agent_config.get('script_template', '')[:200]}...")
    logger.info(f"📥 DIALER RECEIVED FROM TASKS - greeting_outbound: {agent_config.get('greeting_outbound', '')}")

    # Build agent_config payload using model-grounded required fields
    agent_cfg_payload: Dict[str, Any] = {
        "voice_external_id": agent_config.get("voice_external_id"),
        "name": agent_config.get("name"),
        "language": agent_config.get("language"),
        "workspace_name": agent_config.get("workspace_name"),
        "character": agent_config.get("character"),
        "greeting_inbound": agent_config.get("greeting_inbound"),
        "greeting_outbound": agent_config.get("greeting_outbound"),
        "max_call_duration_s": max(1, 60 * int(agent_config["max_call_duration_minutes"])),
        "script": agent_config.get("script_template", ""),
        "workspace_id": agent_config.get("workspace_id"),
        "event_type_id": agent_config.get("event_type_id"),
        "knowledge_documents": agent_config.get("knowledge_documents"),
        "knowledge_content": knowledge_content,
    }
    
    # --- Job metadata sent to the agent process ---
    hotcalls_metadata = {
        "agent": agent_name,
        "call_type": "outbound",
        "to_number": callee_phone,
        "from_number": from_number,
        "call_task_id": call_task_id or lead_data.get("call_task_id", ""),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sip_provider": "jambonz",
        "agent_config": agent_cfg_payload,
        "lead_data": {
            "id": lead_data.get("id"),
            "name": lead_data.get("name"),
            "surname": lead_data.get("surname"),
            "phone": callee_phone,
            "email": lead_data.get("email"),
        },
    }

    try:
        # 0) Validate configuration and input
        if not agent_name:
            return {
                "success": False,
                "error": "LIVEKIT_AGENT_NAME not set",
                "to_number": callee_phone,
                "agent_name": agent_name,
                "abort_reason": "configuration",
            }

        if not callee_phone:
            return {
                "success": False,
                "error": "missing callee phone",
                "to_number": callee_phone,
                "agent_name": agent_name,
                "abort_reason": "invalid_lead",
            }

        # 1) Preflight agent token
        token_check = await preflight_check_agent_token_async(agent_name)
        if not token_check.get("valid"):
            reason = token_check.get("reason") or "token_missing"
            # Preserve reason granularity (e.g., check_failed: <msg>)
            abort_reason = (
                "token_missing" if reason == "token_missing" else
                ("check_failed" if str(reason).startswith("check_failed") else "dispatch_failed")
            )
            return {
                "success": False,
                "error": f"Agent {agent_name}: {reason}",
                "to_number": callee_phone,
                "agent_name": agent_name,
                "abort_reason": abort_reason,
            }

        # 2) Dispatch agent to room with metadata (token can be added by caller if needed)
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

        # 3) Create SIP participant (no experimental args)
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




