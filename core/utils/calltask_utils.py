"""
CallTask feedback loop utilities

This module handles the feedback loop between CallLogs and CallTasks,
automatically updating or deleting CallTasks based on call outcomes.
"""

import logging
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.utils import timezone as dj_timezone
from django.db import connection, transaction
from core.models import CallTask, CallStatus, DisconnectionReason, Lead, User
import hashlib

logger = logging.getLogger(__name__)

# Disconnection reasons that indicate successful call completion
SUCCESS_DISCONNECTION_REASONS = [
    DisconnectionReason.USER_HANGUP,  # User completed call
    DisconnectionReason.AGENT_HANGUP,  # Agent completed call
    DisconnectionReason.CALL_TRANSFER,  # Call was transferred
    DisconnectionReason.VOICEMAIL_REACHED,  # Message left successfully
]

# Disconnection reasons that should trigger retry WITH attempt increment
# These are real attempts where the user actively didn't respond/declined
RETRY_WITH_INCREMENT_REASONS = [
    DisconnectionReason.DIAL_BUSY,  # Line busy - real attempt
    DisconnectionReason.DIAL_FAILED,  # Call failed - real attempt
    DisconnectionReason.DIAL_NO_ANSWER,  # No answer - real attempt
    DisconnectionReason.USER_DECLINED,  # User actively declined
    DisconnectionReason.MARKED_AS_SPAM,  # User marked as spam
]

# Disconnection reasons that indicate permanent failure - DELETE immediately
# These are situations where retrying will never succeed
PERMANENT_FAILURE_REASONS = [
    DisconnectionReason.INVALID_DESTINATION,  # Invalid phone number
    DisconnectionReason.TELEPHONY_PROVIDER_PERMISSION_DENIED,  # Permission denied
    DisconnectionReason.NO_VALID_PAYMENT,  # Account/billing issue
    DisconnectionReason.SCAM_DETECTED,  # Detected as scam
    DisconnectionReason.ERROR_USER_NOT_JOINED,  # User never joined call
]

# Disconnection reasons that should trigger retry WITHOUT attempt increment
# These are technical/system issues, not user rejections
RETRY_WITHOUT_INCREMENT_REASONS = [
    DisconnectionReason.INACTIVITY,  # Timeout, not user fault
    DisconnectionReason.MAX_DURATION_REACHED,  # System limit reached
    DisconnectionReason.CONCURRENCY_LIMIT_REACHED,  # System overload
    DisconnectionReason.ERROR_NO_AUDIO_RECEIVED,  # Technical issue
    DisconnectionReason.ERROR_ASR,  # Speech recognition issue
    DisconnectionReason.SIP_ROUTING_ERROR,  # Network/routing issue
    DisconnectionReason.TELEPHONY_PROVIDER_UNAVAILABLE,  # Provider issue
    DisconnectionReason.ERROR_LLM_WEBSOCKET_OPEN,  # LLM connection issue
    DisconnectionReason.ERROR_LLM_WEBSOCKET_LOST_CONNECTION,
    DisconnectionReason.ERROR_LLM_WEBSOCKET_RUNTIME,
    DisconnectionReason.ERROR_LLM_WEBSOCKET_CORRUPT_PAYLOAD,
    DisconnectionReason.ERROR_HOTCALLS,  # HotCalls system error
    DisconnectionReason.ERROR_UNKNOWN,  # Unknown system error
    DisconnectionReason.REGISTERED_CALL_TIMEOUT,  # System timeout
    DisconnectionReason.PREFLIGHT_CALL_LOG_FAILED,  # Preflight gate failed
]


def find_related_calltask(call_log):
    """
    Find CallTask matching this CallLog.

    Matches by: lead_id, agent_id, and phone number.
    This is sufficient since CallTasks are unique per lead-agent combination.

    Args:
        call_log: CallLog instance

    Returns:
        CallTask instance or None if not found
    """
    try:
        # For outbound calls, match the "to_number" from CallLog with CallTask phone
        return CallTask.objects.filter(
            lead=call_log.lead,
            agent=call_log.agent,
            phone=call_log.to_number,  # Outbound call destination
            status__in=[CallStatus.IN_PROGRESS, CallStatus.CALL_TRIGGERED],
        ).first()

    except Exception as e:
        logger.error(f"Error finding CallTask for CallLog {call_log.id}: {e}")
        return None


def process_calltask_feedback(call_task, call_log):
    """
    Main logic for processing CallTask based on CallLog disconnection reason.

    Args:
        call_task: CallTask instance to update
        call_log: CallLog instance with disconnection info
    """
    disconnection_reason = call_log.disconnection_reason

    logger.info(
        f"Processing CallTask {call_task.id} feedback. Disconnection: {disconnection_reason}"
    )

    if disconnection_reason in SUCCESS_DISCONNECTION_REASONS:
        # DELETE - Call completed successfully
        call_task_id = call_task.id
        call_task.delete()
        logger.info(
            f"CallTask {call_task_id} deleted - successful call ({disconnection_reason})"
        )

    elif disconnection_reason in RETRY_WITH_INCREMENT_REASONS:
        # RETRY with attempt increment
        handle_retry_with_increment(call_task, call_log)

    elif disconnection_reason in PERMANENT_FAILURE_REASONS:
        # DELETE - Permanent failure, no point retrying
        call_task_id = call_task.id
        call_task.delete()
        logger.info(
            f"CallTask {call_task_id} deleted - permanent failure ({disconnection_reason})"
        )

    elif disconnection_reason in RETRY_WITHOUT_INCREMENT_REASONS:
        # RETRY without attempt increment
        handle_retry_without_increment(call_task, call_log)

    else:
        # 🚨 FALLBACK: Unknown/unhandled disconnection reason
        # DELETE to prevent infinite retries and database pollution
        call_task_id = call_task.id
        call_task.delete()
        logger.warning(
            f"CallTask {call_task_id} deleted - unhandled disconnection_reason: {disconnection_reason}. ADD TO APPROPRIATE LIST!"
        )
        logger.warning(
            f"⚠️ MISSING DISCONNECTION REASON CLASSIFICATION: {disconnection_reason} - Update calltask_utils.py"
        )


def handle_retry_with_increment(call_task, call_log):
    """
    Handle retry with attempt increment for real call attempts.

    Args:
        call_task: CallTask to update
        call_log: CallLog with disconnection info
    """
    agent = call_task.agent
    call_task_id = call_task.id

    # Increment attempts using the existing method
    # NOTE: This may DELETE the CallTask if max_retries is reached
    call_task.increment_retries(agent.max_retries)

    # Check if CallTask still exists (not deleted by increment_retries)
    try:
        # Refresh from database to get updated state
        call_task.refresh_from_db()

        # CallTask still exists - set up retry
        call_task.status = CallStatus.RETRY
        call_task.next_call = calculate_next_call_time(agent, timezone.now())
        call_task.save(update_fields=["status", "next_call"])
        logger.info(
            f"CallTask {call_task_id} scheduled for retry at {call_task.next_call} (attempt {call_task.attempts})"
        )

    except CallTask.DoesNotExist:
        # CallTask was deleted by increment_retries - max retries reached
        logger.info(
            f"CallTask {call_task_id} deleted by increment_retries - max retries ({agent.max_retries}) reached"
        )


def handle_retry_without_increment(call_task, call_log):
    """
    Handle retry without attempt increment for technical failures.

    Args:
        call_task: CallTask to update
        call_log: CallLog with disconnection info
    """
    agent = call_task.agent

    # Don't increment attempts - this wasn't user's fault
    call_task.status = CallStatus.RETRY
    call_task.next_call = calculate_next_call_time(agent, timezone.now())
    call_task.save(update_fields=["status", "next_call", "updated_at"])

    logger.info(
        f"CallTask {call_task.id} retrying without increment at {call_task.next_call} (technical failure: {call_log.disconnection_reason})"
    )


def reschedule_without_increment(
    call_task: CallTask, reason: str, hint: str
) -> CallTask:
    """
    Reschedule a CallTask WITHOUT incrementing attempts.
    Used for system failures, preflight issues, or any non-user-caused failures.

    Args:
        call_task: CallTask to update
        reason: Reason for rescheduling (e.g., 'preflight_failed', 'system_error', 'token_missing')
        hint: Detailed error message or description

    Returns:
        The updated CallTask instance
    """
    agent = call_task.agent
    if not agent:
        raise ValueError(f"CallTask {call_task.id} has no agent - cannot reschedule")

    # Keep attempts unchanged
    call_task.status = CallStatus.RETRY
    call_task.next_call = calculate_next_call_time(agent, timezone.now())

    entry = {"reason": reason, "hint": hint, "at": timezone.now().isoformat()}
    reasons_list = call_task.retry_reasons or []
    reasons_list.append(entry)
    # Cap history to the last 30 reasons to avoid unbounded growth
    if len(reasons_list) > 30:
        reasons_list = reasons_list[-30:]
    call_task.retry_reasons = reasons_list

    call_task.save(update_fields=["status", "next_call", "retry_reasons", "updated_at"])
    logger.info(
        f"CallTask {call_task.id} rescheduled without increment ({reason}: {hint}); next_call={call_task.next_call}"
    )
    return call_task


def handle_max_retries(call_task: CallTask) -> bool:
    """
    Early guard: delete the CallTask if it has already reached max retries.

    Returns:
        True if the task was deleted here (max retries reached), False otherwise.
    """
    agent = call_task.agent
    if not agent:
        # No implicit defaults; without an agent we cannot evaluate limits here
        return False

    max_retries = agent.max_retries  # explicit, no defaults
    if call_task.attempts >= max_retries:
        call_task_id = str(call_task.id)
        logger.warning(
            f"🗑️ CallTask {call_task_id} reached max retries ({max_retries}) - deleting early in trigger"
        )
        call_task.delete()
        return True
    return False


def calculate_next_call_time(agent, base_time):
    """
    Calculate next valid call time respecting agent configuration.

    Args:
        agent: Agent instance with retry_interval, workdays, call_from, call_to
        base_time: Base datetime to calculate from

    Returns:
        datetime: Next valid call time
    """
    # Start with base retry interval
    next_time = base_time + timedelta(minutes=max(getattr(agent, "retry_interval", 1), 1))

    # Apply workday/time constraints
    next_time = ensure_valid_call_time(agent, next_time)

    return next_time

    
def _get_agent_local_tz(agent):
    """Return the global project timezone for interpreting agent hours.

    Per requirements, ignore any per-agent or per-calendar time zones and
    consistently use the single `TIME_ZONE` from Django settings. Fallback
    to UTC if misconfigured.
    """
    try:
        return ZoneInfo(getattr(settings, "TIME_ZONE", "UTC"))
    except Exception:
        return ZoneInfo("UTC")


def _normalize_local_time(dt_local, tz):
    """Normalize a settings-TZ aware datetime to handle DST edge cases.

    - If ambiguous, prefer the later occurrence (fold=1)
    - If nonexistent, roll forward minute by minute until round-trip stable
    """
    try:
        # Detect ambiguity by comparing offsets of fold variants
        try:
            off0 = tz.utcoffset(dt_local.replace(fold=0))
            off1 = tz.utcoffset(dt_local.replace(fold=1))
            if off0 != off1:
                dt_local = dt_local.replace(fold=1)
        except Exception:
            pass

        # Resolve nonexistent by round-trip check
        while True:
            utc = dt_local.astimezone(timezone.utc)
            back = timezone.localtime(utc, tz)
            if (
                back.year == dt_local.year
                and back.month == dt_local.month
                and back.day == dt_local.day
                and back.hour == dt_local.hour
                and back.minute == dt_local.minute
            ):
                return dt_local
            dt_local = dt_local + timedelta(minutes=1)
    except Exception:
        return dt_local


def ensure_valid_call_time(agent, datetime_obj):
    """
    Ensure datetime falls within agent's working constraints.

    Args:
        agent: Agent instance with workdays, call_from, call_to config
        datetime_obj: Datetime to validate/adjust

    Returns:
        datetime: Adjusted datetime that respects agent configuration
    """
    # Convert to local timezone if needed
    if timezone.is_naive(datetime_obj):
        datetime_obj = timezone.make_aware(datetime_obj)

    max_iterations = 14  # Prevent infinite loops (2 weeks max)
    iterations = 0

    # Normalize workdays once to handle different capitalizations from DB
    configured_workdays = {d.lower() for d in (agent.workdays or [])}

    # Convert to the agent/workspace local timezone for comparisons
    local_tz = _get_agent_local_tz(agent)
    datetime_obj = timezone.localtime(datetime_obj, local_tz)

    while iterations < max_iterations:
        # Check if current day is a workday in local timezone
        current_weekday = datetime_obj.strftime("%A").lower()

        # Treat empty workdays as all days
        if not configured_workdays:
            configured_workdays = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}

        if current_weekday in configured_workdays:
            # Check if time is within working hours (support overnight windows)
            current_time = datetime_obj.time()

            within_hours = False
            if agent.call_from <= agent.call_to:
                within_hours = agent.call_from <= current_time <= agent.call_to
            else:
                # Overnight window like 22:00–02:00
                within_hours = current_time >= agent.call_from or current_time <= agent.call_to

            if within_hours:
                # Perfect - within workday and working hours (keep in settings TZ)
                return datetime_obj
            elif agent.call_from <= agent.call_to and current_time < agent.call_from:
                # Too early - move to start of working hours today
                datetime_obj = datetime_obj.replace(
                    hour=agent.call_from.hour,
                    minute=agent.call_from.minute,
                    second=0,
                    microsecond=0,
                )
                datetime_obj = _normalize_local_time(datetime_obj, local_tz)
                return datetime_obj
            else:
                # Too late (or in overnight case but before start window) - move to next day start
                datetime_obj = datetime_obj.replace(
                    hour=agent.call_from.hour,
                    minute=agent.call_from.minute,
                    second=0,
                    microsecond=0,
                ) + timedelta(days=1)
                datetime_obj = _normalize_local_time(datetime_obj, local_tz)
        else:
            # Not a workday - advance to next day
            datetime_obj = datetime_obj.replace(
                hour=agent.call_from.hour,
                minute=agent.call_from.minute,
                second=0,
                microsecond=0,
            ) + timedelta(days=1)

        iterations += 1

    # Fallback - if we can't find a valid time, just use the original + retry_interval
    logger.warning(
        f"Could not find valid call time for agent {agent.agent_id}, using fallback"
    )
    # Return in configured TIME_ZONE (it was localized earlier)
    return _normalize_local_time(datetime_obj, local_tz)


def is_valid_call_time(agent, datetime_obj):
    """
    Check if datetime falls within agent's working hours/days.

    Args:
        agent: Agent instance
        datetime_obj: Datetime to check

    Returns:
        bool: True if datetime is valid for calling
    """
    # Check workday in local timezone (normalize configured days from DB)
    configured_workdays = {d.lower() for d in (agent.workdays or [])}
    local_tz = _get_agent_local_tz(agent)
    datetime_obj = _normalize_local_time(timezone.localtime(datetime_obj, local_tz), local_tz)
    current_weekday = datetime_obj.strftime("%A").lower()
    if not configured_workdays:
        configured_workdays = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    if current_weekday not in configured_workdays:
        return False

    # Check working hours (support overnight)
    current_time = datetime_obj.time()
    if agent.call_from <= agent.call_to:
        if not (agent.call_from <= current_time <= agent.call_to):
            return False
    else:
        if not (current_time >= agent.call_from or current_time <= agent.call_to):
            return False

    return True


# ==================
# Target Ref Resolver
# ==================


def parse_target_ref(target_ref: str) -> tuple[str, str]:
    """
    Parse canonical target_ref into (scheme, value).
    Supported schemes: lead, test_user, raw_phone, external:<system>
    """
    if not target_ref:
        return ("", "")
    if target_ref.startswith("lead:"):
        return ("lead", target_ref.split(":", 1)[1])
    if target_ref.startswith("test_user:"):
        return ("test_user", target_ref.split(":", 1)[1])
    return ("", target_ref)


def resolve_call_target(target_ref: str) -> dict:
    """
    Resolve target_ref to a concrete dialing target without performing any calls.
    Assumes target_ref has been pre-validated to allowed schemes (lead, test_user).
    Returns dict with keys: { 'phone': str, 'lead': Lead|None, 'user': User|None, 'meta': dict }
    """
    scheme, value = parse_target_ref(target_ref)

    if scheme == "lead":
        try:
            lead = Lead.objects.get(id=value)
        except Lead.DoesNotExist:
            raise ValueError(f"Lead not found for target_ref: {target_ref}")
        if not lead.phone:
            raise ValueError(f"Lead has no phone number: {lead.id}")
        return {"phone": lead.phone, "lead": lead, "user": None, "meta": {}}

    if scheme == "test_user":
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise ValueError(f"User not found for target_ref: {target_ref}")
        if not getattr(user, "phone", None):
            raise ValueError(f"Test user has no phone number: {user.id}")
        return {"phone": user.phone, "lead": None, "user": user, "meta": {}}

    # Any other scheme is unsupported in the current system
    raise ValueError(
        "Unsupported target_ref scheme. Allowed: lead:<uuid>, test_user:<uuid>"
    )


# ==========================
# Centralized CallTask Create
# ==========================


def preflight_check_agent_token(agent_name: str) -> dict:
    """
    Check if agent has valid token - for preflight checks.

    Args:
        agent_name: Name of the agent to check

    Returns:
        dict: {"valid": bool, "reason": str, "expires_at": datetime or None}
    """
    from django.utils import timezone
    from core.models import LiveKitAgent

    if not agent_name:
        return {"valid": False, "reason": "no_agent_name", "expires_at": None}

    try:
        agent = LiveKitAgent.objects.filter(
            name=agent_name, expires_at__gt=timezone.now()
        ).first()

        if agent:
            return {
                "valid": True,
                "reason": "valid_token",
                "expires_at": agent.expires_at,
            }
        else:
            return {"valid": False, "reason": "token_missing", "expires_at": None}
    except Exception as e:
        logger.error(f"Error checking agent token for {agent_name}: {e}")
        return {"valid": False, "reason": f"check_failed: {str(e)}", "expires_at": None}


async def preflight_check_agent_token_async(agent_name: str) -> dict:
    """
    Async wrapper around preflight_check_agent_token for use in async contexts.
    Uses sync_to_async to avoid blocking the event loop while running ORM code.
    """
    return await sync_to_async(preflight_check_agent_token, thread_sensitive=True)(
        agent_name
    )


def handle_call_success(call_task, call_result: dict) -> dict:
    """
    Handle successful call initiation.
    Call remains IN_PROGRESS until webhook feedback.

    Args:
        call_task: CallTask instance
        call_result: Result from LiveKit call

    Returns:
        dict: Response for Celery task
    """
    # Just update timestamp, keep IN_PROGRESS status
    call_task.updated_at = timezone.now()
    call_task.save(update_fields=["updated_at"])

    return {
        "success": True,
        "call_task_id": str(call_task.id),
        "message": "Call launched; task remains IN_PROGRESS.",
        "result": call_result,
    }


def handle_call_failure(call_task, error: str, abort_reason: str = None) -> dict:
    """
    Dispatch-time failure handler. NEVER increments attempts, NEVER deletes.
    All max-retry checks happen early in trigger_call. Real outcome-based
    increments/deletes are handled by CallLog feedback processing.

    Behavior:
    - token_missing / dispatch_failed     → reschedule_without_increment
    - system errors (timeouts, network)   → reschedule_without_increment('system_error')
    - anything else at dispatch time      → reschedule_without_increment('dispatch_error')
    """
    # Use the real reason; no bucketing/categorization
    reason = abort_reason if abort_reason else (error or "unknown_error")

    # Delegate scheduling to the unified helper (no attempt increment)
    reschedule_without_increment(call_task, reason=reason, hint=error or reason)

    return {
        "success": False,
        "call_task_id": str(call_task.id),
        "message": f"{reason} - rescheduled without incrementing attempts",
        "error": error,
        "attempts": call_task.attempts,
    }


def _hash_to_bigint(value: str) -> int:
    """Hash a string deterministically into a signed 63-bit integer for pg_advisory locks."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    num = int(digest, 16)
    return num % (2**63 - 1)


def _advisory_lock_for_calltask(agent_id: str, workspace_id: str, target_ref: str):
    """Acquire a transaction-scoped advisory lock to serialize CallTask creation for a given target_ref."""
    lock_str = f"calltask|{workspace_id}|{agent_id}|{target_ref}"
    lock_key = _hash_to_bigint(lock_str)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])


def create_call_task_safely(
    *, agent, workspace, target_ref: str, next_call=None
) -> CallTask:
    """
    Create a CallTask in a race-safe, unified way.

    - target_ref is REQUIRED and must be one of: lead:<uuid>, test_user:<uuid>
    - Phone number is resolved from target_ref at creation time and stored on the CallTask
    - Status is ALWAYS set to SCHEDULED; attempts is set to 0
    - Uses a transaction-scoped Postgres advisory lock keyed by (workspace, agent, target_ref)
    """
    if not target_ref:
        raise ValueError("target_ref is required (lead:<uuid> or test_user:<uuid>)")

    scheme, _ = parse_target_ref(target_ref)
    if scheme not in ("lead", "test_user"):
        raise ValueError(
            "Unsupported target_ref scheme. Allowed: lead:<uuid>, test_user:<uuid>"
        )

    resolved = resolve_call_target(target_ref)
    phone = resolved.get("phone")
    lead = resolved.get("lead")

    if not phone:
        raise ValueError(f"Cannot resolve phone from target_ref: {target_ref}")

    if next_call is None:
        # Respect agent working hours at creation time
        next_call = ensure_valid_call_time(agent, dj_timezone.now())

    with transaction.atomic():
        _advisory_lock_for_calltask(str(agent.agent_id), str(workspace.id), target_ref)

        # Do not create tasks for paused agents
        if getattr(agent, "status", "active") != "active":
            raise ValueError("Agent is paused; refusing to create a CallTask")

        call_task = CallTask.objects.create(
            status=CallStatus.SCHEDULED,
            attempts=0,
            phone=phone,
            workspace=workspace,
            lead=lead,
            agent=agent,
            next_call=next_call,
            target_ref=target_ref,
        )

    return call_task
