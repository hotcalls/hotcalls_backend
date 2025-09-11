from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

from asgiref.sync import async_to_sync

from core.models import CallTask, CallStatus
from core.telephony.repositories.call_repo import lock_call_task


@dataclass
class PlaceCallResult:
    success: bool
    room_name: Optional[str] = None
    dispatch_id: Optional[str] = None
    participant_id: Optional[str] = None
    sip_call_id: Optional[str] = None
    abort_reason: Optional[str] = None
    error: Optional[str] = None


class DialerService:
    """
    Orchestrates outbound calls with idempotency by CallTask.
    """

    def __init__(self, logger):
        self.logger = logger

    def place_call_now(
        self,
        call_task_id: str,
        *,
        sip_trunk_id: str,
        agent_config: Dict[str, Any],
        lead_data: Dict[str, Any],
        from_number: str,
        answer_timeout_s: float = 45.0,
    ) -> PlaceCallResult:
        # 1) Idempotency & status transitions
        try:
            with lock_call_task(call_task_id) as call_task:
                # Only short-circuit if a dispatch already succeeded and is active
                if call_task.status == CallStatus.IN_PROGRESS:
                    return PlaceCallResult(True)

                # Ensure status reflects we're about to dispatch
                if call_task.status != CallStatus.CALL_TRIGGERED:
                    call_task.status = CallStatus.CALL_TRIGGERED
                    call_task.save(update_fields=["status"])
        except CallTask.DoesNotExist:
            return PlaceCallResult(False, abort_reason="invalid_call_task", error="CallTask not found")

        # 2) Execute async low-level path
        from ._dialer_async import _make_call_async as low_level
        from ._dialer_async import _fetch_knowledge_content

        knowledge_content = _fetch_knowledge_content(agent_id=agent_config.get("agent_id"), doc_ids=agent_config.get("knowledge_documents", []))

        result = async_to_sync(low_level)(
            sip_trunk_id,
            agent_config,
            lead_data,
            from_number,
            call_task_id=str(call_task.id),
            answer_timeout_s=answer_timeout_s,
            knowledge_content=knowledge_content,
        )

        # 3) Persist outcome & return
        if result.get("success"):
            try:
                with lock_call_task(call_task_id) as call_task:
                    call_task.status = CallStatus.IN_PROGRESS
                    call_task.save(update_fields=["status"])
            except CallTask.DoesNotExist:
                pass
            return PlaceCallResult(
                True,
                room_name=result.get("room_name"),
                dispatch_id=result.get("dispatch_id"),
                participant_id=result.get("participant_id"),
                sip_call_id=result.get("sip_call_id"),
            )

        # Failure paths
        try:
            with lock_call_task(call_task_id) as call_task:
                call_task.status = CallStatus.RETRY
                call_task.increment_retries()
                call_task.save(update_fields=["status"])
        except CallTask.DoesNotExist:
            pass

        return PlaceCallResult(
            False,
            abort_reason=result.get("abort_reason") or "failed",
            error=result.get("error"),
        )


