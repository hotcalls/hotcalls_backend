"""
CallTask feedback loop utilities

This module handles the feedback loop between CallLogs and CallTasks,
automatically updating or deleting CallTasks based on call outcomes.
"""

import logging
from datetime import timedelta
from django.utils import timezone
from core.models import CallTask, CallStatus, DisconnectionReason, Lead, User

logger = logging.getLogger(__name__)

# Disconnection reasons that indicate successful call completion
SUCCESS_DISCONNECTION_REASONS = [
    DisconnectionReason.USER_HANGUP,      # User completed call
    DisconnectionReason.AGENT_HANGUP,     # Agent completed call  
    DisconnectionReason.CALL_TRANSFER,    # Call was transferred
    DisconnectionReason.VOICEMAIL_REACHED, # Message left successfully
]

# Disconnection reasons that should trigger retry WITH attempt increment
# These are real attempts where the user actively didn't respond/declined
RETRY_WITH_INCREMENT_REASONS = [
    DisconnectionReason.DIAL_BUSY,        # Line busy - real attempt
    DisconnectionReason.DIAL_FAILED,      # Call failed - real attempt  
    DisconnectionReason.DIAL_NO_ANSWER,   # No answer - real attempt
    DisconnectionReason.USER_DECLINED,    # User actively declined
    DisconnectionReason.MARKED_AS_SPAM,   # User marked as spam
]

# Disconnection reasons that indicate permanent failure - DELETE immediately
# These are situations where retrying will never succeed
PERMANENT_FAILURE_REASONS = [
    DisconnectionReason.INVALID_DESTINATION,           # Invalid phone number
    DisconnectionReason.TELEPHONY_PROVIDER_PERMISSION_DENIED,  # Permission denied
    DisconnectionReason.NO_VALID_PAYMENT,             # Account/billing issue
    DisconnectionReason.SCAM_DETECTED,                # Detected as scam
    DisconnectionReason.ERROR_USER_NOT_JOINED,        # User never joined call
]

# Disconnection reasons that should trigger retry WITHOUT attempt increment
# These are technical/system issues, not user rejections
RETRY_WITHOUT_INCREMENT_REASONS = [
    DisconnectionReason.INACTIVITY,                    # Timeout, not user fault
    DisconnectionReason.MAX_DURATION_REACHED,          # System limit reached
    DisconnectionReason.CONCURRENCY_LIMIT_REACHED,     # System overload
    DisconnectionReason.ERROR_NO_AUDIO_RECEIVED,       # Technical issue
    DisconnectionReason.ERROR_ASR,                     # Speech recognition issue
    DisconnectionReason.SIP_ROUTING_ERROR,             # Network/routing issue
    DisconnectionReason.TELEPHONY_PROVIDER_UNAVAILABLE, # Provider issue
    DisconnectionReason.ERROR_LLM_WEBSOCKET_OPEN,      # LLM connection issue
    DisconnectionReason.ERROR_LLM_WEBSOCKET_LOST_CONNECTION,
    DisconnectionReason.ERROR_LLM_WEBSOCKET_RUNTIME,
    DisconnectionReason.ERROR_LLM_WEBSOCKET_CORRUPT_PAYLOAD,
    DisconnectionReason.ERROR_HOTCALLS,                  # HotCalls system error
    DisconnectionReason.ERROR_UNKNOWN,                 # Unknown system error
    DisconnectionReason.REGISTERED_CALL_TIMEOUT,       # System timeout
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
            status__in=[CallStatus.IN_PROGRESS, CallStatus.CALL_TRIGGERED]
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
    
    logger.info(f"Processing CallTask {call_task.id} feedback. Disconnection: {disconnection_reason}")
    
    if disconnection_reason in SUCCESS_DISCONNECTION_REASONS:
        # DELETE - Call completed successfully
        call_task_id = call_task.id
        call_task.delete()
        logger.info(f"CallTask {call_task_id} deleted - successful call ({disconnection_reason})")
        
    elif disconnection_reason in RETRY_WITH_INCREMENT_REASONS:
        # RETRY with attempt increment
        handle_retry_with_increment(call_task, call_log)
        
    elif disconnection_reason in PERMANENT_FAILURE_REASONS:
        # DELETE - Permanent failure, no point retrying
        call_task_id = call_task.id
        call_task.delete()
        logger.info(f"CallTask {call_task_id} deleted - permanent failure ({disconnection_reason})")
        
    elif disconnection_reason in RETRY_WITHOUT_INCREMENT_REASONS:
        # RETRY without attempt increment  
        handle_retry_without_increment(call_task, call_log)
        
    else:
        # 🚨 FALLBACK: Unknown/unhandled disconnection reason
        # DELETE to prevent infinite retries and database pollution
        call_task_id = call_task.id
        call_task.delete()
        logger.warning(f"CallTask {call_task_id} deleted - unhandled disconnection_reason: {disconnection_reason}. ADD TO APPROPRIATE LIST!")
        logger.warning(f"⚠️ MISSING DISCONNECTION REASON CLASSIFICATION: {disconnection_reason} - Update calltask_utils.py")


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
        call_task.save(update_fields=['status', 'next_call'])
        logger.info(f"CallTask {call_task_id} scheduled for retry at {call_task.next_call} (attempt {call_task.attempts})")
        
    except CallTask.DoesNotExist:
        # CallTask was deleted by increment_retries - max retries reached
        logger.info(f"CallTask {call_task_id} deleted by increment_retries - max retries ({agent.max_retries}) reached")


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
    call_task.save(update_fields=['status', 'next_call'])
    
    logger.info(f"CallTask {call_task.id} retrying without increment at {call_task.next_call} (technical failure: {call_log.disconnection_reason})")


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
    next_time = base_time + timedelta(minutes=agent.retry_interval)
    
    # Apply workday/time constraints
    next_time = ensure_valid_call_time(agent, next_time)
    
    return next_time


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
    
    while iterations < max_iterations:
        # Check if current day is a workday
        current_weekday = datetime_obj.strftime('%A').lower()
        
        if current_weekday in agent.workdays:
            # Check if time is within working hours
            current_time = datetime_obj.time()
            
            if agent.call_from <= current_time <= agent.call_to:
                # Perfect - within workday and working hours
                return datetime_obj
            elif current_time < agent.call_from:
                # Too early - move to start of working hours today
                datetime_obj = datetime_obj.replace(
                    hour=agent.call_from.hour,
                    minute=agent.call_from.minute,
                    second=0,
                    microsecond=0
                )
                return datetime_obj
            else:
                # Too late - move to next day and try again
                datetime_obj = datetime_obj.replace(
                    hour=agent.call_from.hour,
                    minute=agent.call_from.minute,
                    second=0,
                    microsecond=0
                ) + timedelta(days=1)
        else:
            # Not a workday - advance to next day
            datetime_obj = datetime_obj.replace(
                hour=agent.call_from.hour,
                minute=agent.call_from.minute,
                second=0,
                microsecond=0
            ) + timedelta(days=1)
        
        iterations += 1
    
    # Fallback - if we can't find a valid time, just use the original + retry_interval
    logger.warning(f"Could not find valid call time for agent {agent.agent_id}, using fallback")
    return datetime_obj


def is_valid_call_time(agent, datetime_obj):
    """
    Check if datetime falls within agent's working hours/days.
    
    Args:
        agent: Agent instance
        datetime_obj: Datetime to check
        
    Returns:
        bool: True if datetime is valid for calling
    """
    # Check workday
    current_weekday = datetime_obj.strftime('%A').lower()
    if current_weekday not in agent.workdays:
        return False
    
    # Check working hours
    current_time = datetime_obj.time()
    if not (agent.call_from <= current_time <= agent.call_to):
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
    if target_ref.startswith("raw_phone:"):
        return ("raw_phone", target_ref.split(":", 1)[1])
    if target_ref.startswith("external:"):
        return ("external", target_ref.split(":", 1)[1])
    return ("", target_ref)


def resolve_call_target(target_ref: str) -> dict:
    """
    Resolve target_ref to a concrete dialing target without performing any calls.
    NOTE: Not used by the call flow yet. Present for future use.
    Returns dict with keys: { 'phone': str, 'lead': Lead|None, 'user': User|None, 'meta': dict }
    """
    scheme, value = parse_target_ref(target_ref)
    result = { 'phone': None, 'lead': None, 'user': None, 'meta': {} }
    
    try:
        if scheme == "lead":
            lead = Lead.objects.get(id=value)
            result['lead'] = lead
            result['phone'] = lead.phone
        elif scheme == "test_user":
            user = User.objects.get(id=value)
            result['user'] = user
            result['phone'] = user.phone
        elif scheme == "raw_phone":
            result['phone'] = value
        elif scheme == "external":
            # Placeholder for future external system resolution, e.g., CRM
            system_and_id = value.split(":", 1)
            system = system_and_id[0]
            external_id = system_and_id[1] if len(system_and_id) > 1 else ""
            result['meta'] = { 'external_system': system, 'external_id': external_id }
            # Leave phone None; external resolver would fetch it
        else:
            # Unknown format; treat as raw phone if it looks like E.164
            result['phone'] = value if value.startswith('+') else None
    except (Lead.DoesNotExist, User.DoesNotExist):
        # Keep result with None phone; caller should handle
        pass
    
    return result
