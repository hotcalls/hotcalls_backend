"""
Celery tasks for HotCalls application – *fully fool‑proof* version.

Key improvements
────────────────
1.  **Redis distributed lock** (SETNX with TTL) guarantees that at most ONE
    `schedule_agent_call` task body runs anywhere in the cluster.
2.  **SingletonTask** base class adds a second layer of protection:
    if the Redis lock somehow fails, the Celery task itself cannot overlap.
3.  **Atomic jerk‑off**: a single `UPDATE … WHERE id=? AND status IN (…)`
    changes a CallTask's status to `CALL_TRIGGERED`.  If the row was already
    touched, the update count is 0 and we do *not* fire `trigger_call.delay`.
4.  **No silent falls‑through** – every failure path is logged and returned.
5.  The original hefty `select_for_update()` blocks are kept **inside**
    `trigger_call` (where they belong) so call‑level race conditions are still
    covered.

This file completely replaces your previous core/tasks.py.
"""
import logging
import traceback
from datetime import timedelta

import redis
from celery import Task, shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Case, IntegerField, When
from django.utils import timezone
# Token import removed - no longer using DRF token authentication

# ─────────────────────────────
# Redis client for locking
# ─────────────────────────────
REDIS_URL = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
redis_client = redis.StrictRedis.from_url(REDIS_URL)

# ─────────────────────────────
# Logging
# ─────────────────────────────
logger = logging.getLogger(__name__)


# ─────────────────────────────
# Singleton (distributed‑lock) Celery base class
# ─────────────────────────────
class SingletonTask(Task):
    """
    Ensures that only **one** instance of the task executes cluster‑wide.

    • Acquires a Redis lock `<lock:<task‑name>>` with TTL = `lock_ttl` seconds.
    • If the lock cannot be acquired, the task aborts immediately.
    • The lock is released in `finally` so even if the task crashes,
      it will be freed after the TTL expires.
    """

    # seconds – must be >= the worst‑case runtime of the task body
    lock_ttl = 120

    def __call__(self, *args, **kwargs):
        lock_key = f"lock:{self.name}"
        have_lock = redis_client.set(lock_key, "1", nx=True, ex=self.lock_ttl)
        if not have_lock:
            logger.warning(
                f"🛑 {self.name}: another instance already holds the Redis lock; skipping."
            )
            return {
                "success": False,
                "error": "singleton_lock_busy",
                "message": "Another task instance is still running.",
            }

        try:
            return self.run(*args, **kwargs)  # run actual task code
        finally:
            try:
                redis_client.delete(lock_key)
            except Exception as lock_release_err:
                logger.error(
                    f"🔓 {self.name}: failed to release Redis lock – {lock_release_err}"
                )


# ─────────────────────────────
# 1) Simple hello‑world test
# ─────────────────────────────
@shared_task(bind=True, name="core.tasks.hello_world_test")
def hello_world_test(self):
    """
    Sanity‑check that Celery workers pick up tasks.
    """
    try:
        worker_name = self.request.hostname
        timestamp = timezone.now().isoformat()
        logger.info(f"🌍 Hello World from {worker_name} at {timestamp}")
        return {
            "message": "Hello World from Celery!",
            "worker": worker_name,
            "timestamp": timestamp,
            "task_id": self.request.id,
        }
    except Exception as e:
        logger.error(f"❌ Hello world task failed: {e}")
        return {"error": str(e), "timestamp": timezone.now().isoformat()}


# ─────────────────────────────
# 2) Trigger a single outbound call
# ─────────────────────────────
@shared_task(bind=True, name="core.tasks.trigger_call")
def trigger_call(self, call_task_id):
    """
    Invoked **only** by `schedule_agent_call`.

    Flow:
      1. Double-check status is CALL_TRIGGERED.
      2. Move to IN_PROGRESS (inside atomic tx).
      3. Check quotas (skip for test calls where lead is null).
      4. Launch the LiveKit outbound call (async).
      5. • If call launch succeeds → keep IN_PROGRESS (do NOT change status).
         • If call launch fails     → RETRY / WAITING logic.
      6. External webhook / feedback loop will delete or close the task.
    """
    # Function-level imports (avoid inner-block imports; still avoids module-level cycles)
    from core.models import CallTask, CallStatus
    from core.utils.calltask_utils import (
        handle_max_retries,
        handle_call_success,
        handle_call_failure,
    )
    from core.quotas import enforce_and_record, QuotaExceeded

    try:
        call_task = CallTask.objects.get(id=call_task_id)
    except CallTask.DoesNotExist:
        logger.error(f"❌ CallTask {call_task_id} vanished before trigger.")
        return {"success": False, "error": "calltask_missing", "id": call_task_id}

    # Guard‑rail: only proceed if it is *still* CALL_TRIGGERED
    if call_task.status != CallStatus.CALL_TRIGGERED:
        logger.warning(
            f"⚠️ trigger_call: task {call_task_id} in status {call_task.status}; abort."
        )
        return {"success": False, "reason": "stale_trigger", "status": call_task.status}

    # Entire call‑init phase wrapped in a DB transaction for safety
    try:
        with transaction.atomic():
            # Lock *this* row – prevents double‑processing by a rogue duplicate trigger
            call_task = CallTask.objects.select_for_update().get(id=call_task_id)

            if call_task.status != CallStatus.CALL_TRIGGERED:
                return {
                    "success": False,
                    "reason": "status_changed_inside_tx",
                    "status": call_task.status,
                }

            # EARLY MAX-RETRIES GUARD (no defaults; uses agent config)
            if handle_max_retries(call_task):
                return {
                    "success": False,
                    "call_task_id": call_task_id,
                    "message": "Max retries reached - task deleted before dispatch",
                    "deleted": True,
                }

            # Do not move to IN_PROGRESS yet. Only mark IN_PROGRESS after a successful
            # call dispatch; leave as CALL_TRIGGERED until then.
            call_task.save(update_fields=["updated_at"])  # just touch timestamp

        # Extract all payload *outside* the lock
        agent = call_task.agent
        workspace = call_task.workspace
        lead = call_task.lead

        # Get SIP trunk ID from agent's phone number (required)
        phone_obj = getattr(agent, "phone_number", None)
        sip_trunk = getattr(phone_obj, "sip_trunk", None)
        sip_trunk_id = getattr(sip_trunk, "livekit_trunk_id", None)

        agent_config = {
            "name": agent.name,
            "voice_external_id": (agent.voice.voice_external_id if agent.voice else None),
            "language": agent.language,
            # New field propagated to runtime
            "script_template": getattr(agent, "script_template", ""),
            "greeting_outbound": agent.greeting_outbound,
            "greeting_inbound": agent.greeting_inbound,
            "character": agent.character,
            # Provide max duration to agent runtime; convert minutes→seconds downstream
            "max_call_duration_minutes": agent.max_call_duration_minutes,
            "workspace_name": workspace.workspace_name,
            "sip_trunk_id": sip_trunk_id,  # Pass dynamic trunk ID
            # Pass booking identifiers
            "workspace_id": str(workspace.id),
            "event_type_id": (str(agent.event_type_id) if getattr(agent, 'event_type_id', None) else None),
        }
        if lead is not None:
            lead_data = {
                "id": str(lead.id),
                "name": lead.name,
                "surname": lead.surname,
                "email": lead.email,
                "phone": lead.phone,
                "call_task_id": str(call_task.id),
            }
        else:
            # Test call: only pass minimal, non-fallback data
            lead_data = {
                "id": str(call_task.id),
                "phone": call_task.phone,
                "call_task_id": str(call_task.id),
            }

        # Require an agent phone number (no env fallback)
        phone_obj = getattr(agent, "phone_number", None)
        from_number = getattr(phone_obj, "phonenumber", None)

        # 🎯 QUOTA ENFORCEMENT: Skip quotas for test calls (lead is null)
        if lead is not None:
            # Only enforce quotas for real calls with leads
            try:
                # Check quota without recording usage (amount=0)
                enforce_and_record(
                    workspace=workspace,
                    route_name="internal:outbound_call",
                    http_method="POST",
                    amount=0,  # Just check status, don't pre-charge
                )

            except QuotaExceeded as quota_err:
                logger.warning(
                    f"🚫 Call quota exceeded for workspace {workspace.id}: {quota_err}"
                )
                # DELETE this call task - quota exceeded
                with transaction.atomic():
                    call_task = CallTask.objects.select_for_update().get(
                        id=call_task_id
                    )
                    call_task.delete()
                return {
                    "success": False,
                    "call_task_id": call_task_id,
                    "error": "quota_exceeded",
                    "message": f"Call task deleted - {quota_err}",
                }
            except Exception as quota_err:
                # Log error but don't block the call on quota system failures
                logger.error(
                    f"⚠️ Quota check failed for workspace {workspace.id}: {quota_err}"
                )
                # Allow call to proceed
        else:
            # Test call (lead is null) - skip quota enforcement
            logger.info(
                f"🧪 Test call detected (lead is null) - skipping quota enforcement for workspace {workspace.id}"
            )

        # 🚀 Quota OK - Place the outbound call via DialerService
        from core.telephony.services.dialer_service import DialerService
        dialer_service = DialerService(logger)
        service_result = dialer_service.place_call_now(
            call_task_id=str(call_task.id),
            sip_trunk_id=sip_trunk_id,
            agent_config=agent_config,
            lead_data=lead_data,
            from_number=from_number,
        )

        # Shape a response for Celery task; statuses are handled inside the service
        if service_result.success:
            result_payload = {
                "success": True,
                "room_name": service_result.room_name,
                "dispatch_id": service_result.dispatch_id,
                "participant_id": service_result.participant_id,
                "sip_call_id": service_result.sip_call_id,
            }
            with transaction.atomic():
                call_task = CallTask.objects.select_for_update().get(id=call_task_id)
                return handle_call_success(call_task, result_payload)
        else:
            with transaction.atomic():
                call_task = CallTask.objects.select_for_update().get(id=call_task_id)
                return handle_call_failure(
                    call_task,
                    service_result.error,
                    service_result.abort_reason or "failed",
                )

    except Exception as err:
        logger.error(f"❌ trigger_call exception for {call_task_id}: {err}")
        traceback.print_exc()
        # Reschedule without increment; early max-retries guard will handle deletion on next cycle
        try:
            with transaction.atomic():
                call_task = CallTask.objects.select_for_update().get(id=call_task_id)
                result = handle_call_failure(call_task, str(err), "trigger_exception")
                return result
        except Exception:
            pass
        return {"success": False, "error": str(err), "call_task_id": call_task_id}


# ─────────────────────────────
# 3) **THE** periodic scheduler – singleton & fool‑proof
# ─────────────────────────────
@shared_task(
    bind=True,
    name="core.tasks.schedule_agent_call",
    base=SingletonTask,  # ① task‑level singleton
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def schedule_agent_call(self):
    """
    Runs every few seconds.  Promotes ready CallTasks → CALL_TRIGGERED and
    fires `trigger_call.delay()` **only** when the promotion succeeded.

    Fully protected by:
        • SingletonTask (task level)
        • Redis lock (cluster level)
        • Atomic UPDATE (row level)
    """

    # ② cluster‑wide Redis lock (belt‑and‑braces)
    redis_lock_key = "lock:schedule_agent_call_body"
    redis_lock_ttl = 90
    have_lock = redis_client.set(redis_lock_key, "1", nx=True, ex=redis_lock_ttl)
    if not have_lock:
        logger.warning("🛑 schedule_agent_call body already running elsewhere.")
        return {"success": False, "error": "body_lock_busy"}

    from core.models import CallTask, CallStatus  # local import

    try:
        now = timezone.now()

        total_concurrency = 100  # Default concurrency limit
        concurrency_limit = max(
            total_concurrency, 1
        )  # At least 1 to prevent division by zero

        in_progress = CallTask.objects.filter(status=CallStatus.IN_PROGRESS).count()
        call_triggered_cnt = CallTask.objects.filter(status=CallStatus.CALL_TRIGGERED).count()
        available_slots = max(concurrency_limit - (in_progress + call_triggered_cnt), 0)

        if available_slots == 0:
            return {
                "success": True,
                "message": "No capacity; skipping.",
                "in_progress": in_progress,
                "call_triggered": call_triggered_cnt,
                "limit": concurrency_limit,
            }

        # Pull candidate tasks (order: WAITING, SCHEDULED, RETRY, by next_call)
        candidates = (
            CallTask.objects.filter(
                next_call__lte=now,
                status__in=[
                    CallStatus.WAITING,
                    CallStatus.SCHEDULED,
                    CallStatus.RETRY,
                ],
                agent__status="active",
            )
            .select_related("agent", "agent__phone_number", "agent__phone_number__sip_trunk", "workspace")
            .annotate(
                priority=Case(
                    When(status=CallStatus.WAITING, then=1),
                    When(status=CallStatus.SCHEDULED, then=2),
                    When(status=CallStatus.RETRY, then=3),
                    default=4,
                    output_field=IntegerField(),
                )
            )
            .order_by("priority", "next_call")[
                : available_slots * 2
            ]  # over‑fetch a bit
        )

        triggered_ids = []
        for task in candidates:
            # Phone‑conflict check
            conflict = CallTask.objects.filter(
                phone=task.phone,
                status__in=[CallStatus.IN_PROGRESS, CallStatus.CALL_TRIGGERED],
            ).exclude(id=task.id)
            if conflict.exists():
                continue

            # Pre‑promotion config preflight via utils
            try:
                from core.utils.calltask_utils import preflight_dispatch_config
                with transaction.atomic():
                    ct = CallTask.objects.select_for_update().get(id=task.id)
                    pre = preflight_dispatch_config(ct)
                if not pre.get("ok"):
                    continue
            except Exception as preflight_err:
                logger.error(f"⚠️ Pre-promotion preflight failed for task {task.id}: {preflight_err}")
                continue

            # ③ atomic hand‑off
            rows_updated = CallTask.objects.filter(
                id=task.id,
                status__in=[
                    CallStatus.WAITING,
                    CallStatus.SCHEDULED,
                    CallStatus.RETRY,
                ],
                next_call__lte=now,
                updated_at=task.updated_at,
            ).update(status=CallStatus.CALL_TRIGGERED, updated_at=now)
            if rows_updated == 1:
                trigger_call.delay(str(task.id))
                triggered_ids.append(str(task.id))
                if len(triggered_ids) >= available_slots:
                    break  # we filled the capacity

        return {
            "success": True,
            "triggered": len(triggered_ids),
            "task_ids": triggered_ids,
            "available_slots": available_slots,
            "in_progress": in_progress,
            "call_triggered": call_triggered_cnt,
            "concurrency_limit": concurrency_limit,
            "timestamp": now.isoformat(),
        }

    except Exception as e:
        logger.error(f"❌ schedule_agent_call failed: {e}")
        traceback.print_exc()
        raise  # let autoretry handle

    finally:
        try:
            redis_client.delete(redis_lock_key)
        except Exception:
            pass


# ─────────────────────────────
# 4) Minute‑ly stuck‑task garbage collector (unchanged)
# ─────────────────────────────
@shared_task(bind=True, name="core.tasks.cleanup_stuck_call_tasks")
def cleanup_stuck_call_tasks(self):
    """
    Kill CALL_TRIGGERED older than 10 min and IN_PROGRESS older than 30 min.
    """
    from core.models import CallTask, CallStatus

    now = timezone.now()
    trig_thresh = now - timedelta(minutes=10)
    # Threshold comes from per-agent setting; default 30
    from core.models import Agent
    from django.db.models import Min
    # Use the minimum across active agents to be conservative if needed
    try:
        min_minutes = Agent.objects.filter(status="active").aggregate(m=Min("max_call_duration_minutes"))["m"]
    except Exception:
        min_minutes = None
    if not min_minutes:
        min_minutes = 30
    prog_thresh = now - timedelta(minutes=min_minutes)

    try:
        with transaction.atomic():
            trig_q = CallTask.objects.select_for_update().filter(
                status=CallStatus.CALL_TRIGGERED, updated_at__lt=trig_thresh
            )
            prog_q = CallTask.objects.select_for_update().filter(
                status=CallStatus.IN_PROGRESS, updated_at__lt=prog_thresh
            )
            trig_ids = list(trig_q.values_list("id", flat=True))
            prog_ids = list(prog_q.values_list("id", flat=True))
            trig_deleted = trig_q.delete()[0]
            prog_deleted = prog_q.delete()[0]

        if trig_deleted or prog_deleted:
            logger.warning(
                f"🧹 Deleted stuck tasks: {trig_deleted} CALL_TRIGGERED, "
                f"{prog_deleted} IN_PROGRESS"
            )

        return {
            "success": True,
            "deleted_triggered": trig_deleted,
            "deleted_progress": prog_deleted,
            "triggered_ids": trig_ids,
            "progress_ids": prog_ids,
            "timestamp": now.isoformat(),
        }

    except Exception as e:
        logger.error(f"❌ Cleanup stuck call tasks failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "deleted_triggered": 0,
            "deleted_progress": 0,
            "total_deleted": 0,
            "timestamp": timezone.now().isoformat(),
        }


# ─────────────────────────────
# 5) CallTask Feedback Loop
# ─────────────────────────────
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="core.tasks.update_calltask_from_calllog",
)
def update_calltask_from_calllog(self, call_log_id, calltask_id: str):
    """
    Process CallLog and update/delete corresponding CallTask based on call outcome.

    This task provides the feedback loop between call completion (CallLog) and
    call scheduling (CallTask). It automatically:
    - Deletes CallTasks for successful calls
    - Schedules retries for failed calls (with proper agent configuration)
    - Respects agent retry limits and working hours

    Args:
        call_log_id (str): UUID of the CallLog to process
        calltask_id (str): If provided, directly link to this CallTask ID

    Returns:
        dict: Processing result with status and details
    """
    from core.models import CallLog
    from core.utils.calltask_utils import (
        SUCCESS_DISCONNECTION_REASONS,
        PERMANENT_FAILURE_REASONS,
        RETRY_WITH_INCREMENT_REASONS,
        RETRY_WITHOUT_INCREMENT_REASONS,
        handle_retry_with_increment,
        handle_retry_without_increment,
    )

    try:
        # Get the CallLog
        try:
            call_log = CallLog.objects.get(id=call_log_id)
        except CallLog.DoesNotExist:
            logger.error(f"CallLog {call_log_id} not found for feedback processing")
            return {
                "success": False,
                "error": "CallLog not found",
                "call_log_id": call_log_id,
            }

        # Direct link by provided CallTask ID (required)
        try:
            from core.models import CallTask
            call_task = CallTask.objects.get(id=calltask_id)
            logger.info(
                f"Directly linked CallTask {calltask_id} for CallLog {call_log_id}"
            )
        except CallTask.DoesNotExist:
            logger.info(
                f"No CallTask found for CallLog {call_log_id} with id {calltask_id}"
            )
            return "not_found"

        # At this point call_task is guaranteed to exist (earlier return on not found)

        # Process the feedback (moved KISS logic here to avoid cross-module indirection)
        reason = call_log.disconnection_reason
        match reason:
            case r if r in SUCCESS_DISCONNECTION_REASONS:
                # DELETE - Call completed successfully
                call_task_id = call_task.id
                call_task.delete()
                logger.info(f"CallTask {call_task_id} deleted - successful call ({reason})")
                return "deleted"
            case r if r in PERMANENT_FAILURE_REASONS:
                # DELETE - Permanent failure, no retries
                call_task_id = call_task.id
                call_task.delete()
                logger.info(f"CallTask {call_task_id} deleted - permanent failure ({reason})")
                return "deleted"
            case r if r in RETRY_WITH_INCREMENT_REASONS:
                handle_retry_with_increment(call_task, call_log)
                logger.info(f"CallTask {call_task.id} scheduled for retry with increment ({reason})")
                return call_task.status
            case r if r in RETRY_WITHOUT_INCREMENT_REASONS:
                handle_retry_without_increment(call_task, call_log)
                logger.info(f"CallTask {call_task.id} scheduled for retry without increment ({reason})")
                return call_task.status
            case _:
                # Default: retry with increment
                handle_retry_with_increment(call_task, call_log)
                logger.info(f"CallTask {call_task.id} scheduled for retry with increment (default for {reason})")
                return call_task.status

    except Exception as exc:
        logger.error(f"CallTask feedback failed for CallLog {call_log_id}: {exc}")

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2**self.request.retries)  # Exponential backoff
            logger.info(
                f"Retrying CallTask feedback in {retry_delay}s (attempt {self.request.retries + 1})"
            )
            raise self.retry(exc=exc, countdown=retry_delay)
        else:
            # Max retries reached - log error and give up
            logger.error(
                f"CallTask feedback failed permanently for CallLog {call_log_id} after {self.max_retries} retries"
            )
            return "error"


# ===== GOOGLE CALENDAR TOKEN MANAGEMENT =====


@shared_task(bind=True, max_retries=3)
def refresh_google_calendar_connections(self):
    """
    Refresh Google Calendar OAuth tokens 30 days before expiry.
    Uses GoogleCalendar model which now holds OAuth credentials.

    Runs daily at midnight.
    """
    from core.models import GoogleCalendar
    from django.utils import timezone
    from datetime import timedelta
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    import logging

    logger = logging.getLogger(__name__)

    now = timezone.now()
    refresh_threshold = now + timedelta(days=30)  # Refresh 30 days before expiry

    # Query calendars that need refresh
    calendars_to_refresh = GoogleCalendar.objects.filter(
        token_expires_at__lt=refresh_threshold,
        token_expires_at__gt=now,  # Not already expired
        calendar__active=True,  # Calendar is active
        refresh_token__isnull=False,
    ).exclude(refresh_token="")

    results = {
        "total_checked": calendars_to_refresh.count(),
        "refreshed_successfully": 0,
        "failed_refresh": 0,
        "needs_reauth": [],
        "errors": [],
    }

    logger.info(
        f"🔄 Starting Google OAuth token refresh for {results['total_checked']} calendars"
    )

    for google_cal in calendars_to_refresh:
        try:
            # Create credentials object
            credentials = Credentials(
                token=google_cal.access_token,
                refresh_token=google_cal.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                scopes=google_cal.scopes,
            )

            # Refresh the token
            request = Request()
            credentials.refresh(request)

            # Update calendar with new tokens
            google_cal.access_token = credentials.token
            google_cal.token_expires_at = (
                timezone.make_aware(credentials.expiry) if credentials.expiry else None
            )
            google_cal.save(
                update_fields=["access_token", "token_expires_at", "updated_at"]
            )

            results["refreshed_successfully"] += 1
            logger.info(f"✅ Refreshed token for {google_cal.account_email}")

        except Exception as e:
            error_msg = str(e)
            results["failed_refresh"] += 1
            results["errors"].append(
                {"calendar": google_cal.account_email, "error": error_msg}
            )

            # Check if re-auth is needed
            if any(
                keyword in error_msg.lower()
                for keyword in ["invalid_grant", "refresh_token", "authorization"]
            ):
                results["needs_reauth"].append(google_cal.account_email)
                logger.error(
                    f"🚨 Re-authorization needed for {google_cal.account_email}: {error_msg}"
                )

                # Mark calendar as inactive
                google_cal.calendar.active = False
                google_cal.calendar.save(update_fields=["active", "updated_at"])
            else:
                logger.error(
                    f"❌ Unexpected error refreshing {google_cal.account_email}: {error_msg}"
                )

    logger.info(f"""
    🔄 Google Token Refresh Summary:
    ✅ Successfully refreshed: {results["refreshed_successfully"]}
    ❌ Failed to refresh: {results["failed_refresh"]}
    🚨 Need re-authorization: {len(results["needs_reauth"])}
    """)

    return results
@shared_task(bind=True, max_retries=3)
def refresh_microsoft_calendar_connections(self):
    """
    Refresh Outlook Calendar OAuth tokens 30 days before expiry.
    Uses OutlookCalendar model which now holds OAuth credentials.
    """
    from core.models import OutlookCalendar
    from core.services.outlook_calendar import OutlookCalendarService
    now = timezone.now()
    refresh_threshold = now + timedelta(days=30)
    calendars = OutlookCalendar.objects.filter(
        token_expires_at__lt=refresh_threshold,
        token_expires_at__gt=now,
        calendar__active=True,
        refresh_token__isnull=False
    ).exclude(refresh_token='')
    results = {
        'total_checked': calendars.count(),
        'refreshed_successfully': 0,
        'failed_refresh': 0,
        'needs_reauth': [],
        'errors': []
    }
    for outlook_cal in calendars:
        try:
            service = OutlookCalendarService()
            token = service.refresh_tokens(outlook_cal.refresh_token)
            outlook_cal.access_token = token.get('access_token')
            outlook_cal.refresh_token = token.get('refresh_token') or outlook_cal.refresh_token
            outlook_cal.token_expires_at = timezone.now() + timedelta(seconds=int(token.get('expires_in', 3600)))
            outlook_cal.save(update_fields=['access_token', 'refresh_token', 'token_expires_at', 'updated_at'])
            results['refreshed_successfully'] += 1
        except Exception as e:
            error_msg = str(e)
            results['failed_refresh'] += 1
            results['errors'].append({'calendar': outlook_cal.primary_email, 'error': error_msg})
            if any(k in error_msg.lower() for k in ['invalid_grant', 'refresh_token', 'authorization']):
                results['needs_reauth'].append(outlook_cal.primary_email)
                outlook_cal.calendar.active = False
                outlook_cal.calendar.save(update_fields=['active', 'updated_at'])
    return results


# MicrosoftSubscription renewal task removed - MicrosoftSubscription model no longer exists


@shared_task(bind=True, name="core.tasks.cleanup_orphan_router_subaccounts")
def cleanup_orphan_router_subaccounts(self):
    """
    Remove router SubAccount rows that reference non-existent provider-specific
    sub-accounts and delete any EventTypes that end up with no mappings.

    Also removes EventTypes that were already orphaned (zero mappings), which
    will cascade-delete their working hours via FK on_delete=CASCADE.

    Runs every 5 minutes via beat.
    """
    from core.models import (
        SubAccount,
        GoogleSubAccount,
        OutlookSubAccount,
        EventType,
    )
    from django.db import transaction

    checked_subaccounts = 0
    deleted_subaccounts = 0
    deleted_event_types = 0
    errors = 0

    # 1) Delete router SubAccount rows whose provider-specific record no longer exists
    qs = SubAccount.objects.all().only("id", "provider", "sub_account_id")
    for sub in qs.iterator(chunk_size=500):
        checked_subaccounts += 1
        try:
            provider = (sub.provider or "").lower()
            exists = False
            if provider == "google":
                exists = GoogleSubAccount.objects.filter(id=sub.sub_account_id).exists()
            elif provider == "outlook":
                exists = OutlookSubAccount.objects.filter(id=sub.sub_account_id).exists()
            # Unknown provider types are considered invalid
            if not exists:
                with transaction.atomic():
                    current = SubAccount.objects.select_for_update().filter(id=sub.id)
                    if current.exists():
                        current.delete()  # cascades EventTypeSubAccountMapping
                        deleted_subaccounts += 1
        except Exception as e:
            errors += 1
            logger.warning(
                f"cleanup_orphan_router_subaccounts: failed for {sub.id}: {e}"
            )

    # 2) Delete EventTypes with zero mappings (fully orphaned templates)
    try:
        orphan_eventtypes = (
            EventType.objects
            .filter(calendar_mappings__isnull=True)
            .distinct()
        )
        # The above returns EventTypes that have no mappings due to join being null
        # However, some DBs require an explicit left join pattern; do a safety pass too
        orphan_ids = list(orphan_eventtypes.values_list("id", flat=True))
        if not orphan_ids:
            # Fallback: compute via annotation count
            from django.db.models import Count
            orphan_ids = list(
                EventType.objects
                .annotate(mcount=Count("calendar_mappings"))
                .filter(mcount=0)
                .values_list("id", flat=True)
            )
        if orphan_ids:
            deleted_event_types = (
                EventType.objects.filter(id__in=orphan_ids).delete()[0]
            )
    except Exception as e:
        errors += 1
        logger.warning(f"cleanup_orphan_router_subaccounts: eventtype sweep failed: {e}")

    result = {
        "checked_subaccounts": checked_subaccounts,
        "deleted_subaccounts": deleted_subaccounts,
        "deleted_event_types": deleted_event_types,
        "errors": errors,
    }
    logger.info(f"🧹 Router+EventType cleanup: {result}")
    return result

@shared_task(bind=True, max_retries=3)
def refresh_calendar_subaccounts(self):
    """
    Periodically refresh sub-accounts for all active calendars.
    Discovers new shared/delegated calendars that were added after initial OAuth.
    
    Runs daily at 2 AM.
    """
    from core.models import GoogleCalendar, GoogleSubAccount, OutlookCalendar
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    # requests not needed here
    import logging
    
    logger = logging.getLogger(__name__)
    
    results = {
        'google': {'checked': 0, 'new_subaccounts': 0, 'errors': []},
        'outlook': {'checked': 0, 'new_subaccounts': 0, 'errors': []}
    }
    
    # Refresh Google sub-accounts
    for google_cal in GoogleCalendar.objects.filter(calendar__active=True):
        try:
            results['google']['checked'] += 1
            
            # Build Google service
            creds = Credentials(
                token=google_cal.access_token,
                refresh_token=google_cal.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                scopes=google_cal.scopes
            )
            
            service = build('calendar', 'v3', credentials=creds)
            calendar_list = service.calendarList().list().execute()
            
            for cal_entry in calendar_list.get('items', []):
                # Skip primary calendar (already exists as 'self')
                if cal_entry.get('primary'):
                    continue
                
                cal_id = cal_entry.get('id', '')
                access_role = cal_entry.get('accessRole', 'reader')
                
                # Determine relationship
                if '@group.calendar.google.com' in cal_id:
                    relationship = 'shared'
                elif '@resource.calendar.google.com' in cal_id:
                    relationship = 'resource'
                elif access_role in ['owner', 'writer']:
                    relationship = 'delegate'
                else:
                    relationship = 'shared'
                
                # Create sub-account if it doesn't exist
                _, created = GoogleSubAccount.objects.get_or_create(
                    google_calendar=google_cal,
                    act_as_email=cal_id,
                    defaults={
                        'relationship': relationship,
                        'active': True
                    }
                )
                if created:
                    results['google']['new_subaccounts'] += 1
                    logger.info(f"Created new Google sub-account: {cal_id}")
                    
        except Exception as e:
            results['google']['errors'].append({
                'calendar': google_cal.account_email,
                'error': str(e)
            })
            logger.error(f"Error refreshing Google sub-accounts for {google_cal.account_email}: {e}")
    
    # Refresh Outlook sub-accounts via centralized discovery (avoids blank rows)
    from core.services.outlook_calendar import OutlookCalendarService
    for outlook_cal in OutlookCalendar.objects.filter(calendar__active=True):
        try:
            results['outlook']['checked'] += 1
            created_upns = OutlookCalendarService().discover_and_update_sub_accounts(outlook_cal)
            results['outlook']['new_subaccounts'] += len(created_upns)
        except Exception as e:
            results['outlook']['errors'].append({
                'calendar': outlook_cal.primary_email,
                'error': str(e)
            })
            logger.error(f"Error refreshing Outlook sub-accounts for {outlook_cal.primary_email}: {e}")
    
    logger.info(f"""
    📅 Sub-Account Refresh Summary:
    Google: {results['google']['checked']} checked, {results['google']['new_subaccounts']} new
    Outlook: {results['outlook']['checked']} checked, {results['outlook']['new_subaccounts']} new
    """)
    
    return results


@shared_task(bind=True, max_retries=3)
def refresh_meta_tokens(self):
    """
    Refresh Meta (Facebook/Instagram) OAuth tokens 30 days before expiry.

    Runs daily at midnight.
    """
    from core.models import MetaIntegration
    from core.services.meta_integration import MetaIntegrationService
    from django.utils import timezone
    from datetime import timedelta
    import logging

    logger = logging.getLogger(__name__)

    now = timezone.now()
    refresh_threshold = now + timedelta(days=30)  # Refresh 30 days before expiry

    # Query integrations that need refresh
    integrations_to_refresh = MetaIntegration.objects.filter(
        access_token_expires_at__lt=refresh_threshold,
        access_token_expires_at__gt=now,  # Not already expired
        status="active",
    )

    results = {
        "total_checked": integrations_to_refresh.count(),
        "refreshed_successfully": 0,
        "failed_refresh": 0,
        "needs_reauth": [],
        "errors": [],
    }

    logger.info(
        f"🔄 Starting Meta OAuth token refresh for {results['total_checked']} integrations"
    )

    meta_service = MetaIntegrationService()

    for integration in integrations_to_refresh:
        try:
            # Meta uses long-lived tokens that last 60 days
            # Refresh by exchanging the current token for a new long-lived token
            token_data = meta_service.get_long_lived_token(integration.access_token)

            # Update integration with new token
            integration.access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 5184000)  # Default 60 days
            integration.access_token_expires_at = now + timedelta(seconds=expires_in)
            integration.save(
                update_fields=["access_token", "access_token_expires_at", "updated_at"]
            )

            results["refreshed_successfully"] += 1
            logger.info(
                f"✅ Refreshed token for {integration.page_name} (Workspace: {integration.workspace.workspace_name})"
            )

        except Exception as e:
            error_msg = str(e)
            results["failed_refresh"] += 1
            results["errors"].append(
                {
                    "integration": f"{integration.page_name} ({integration.workspace.workspace_name})",
                    "error": error_msg,
                }
            )

            # Check if re-auth is needed
            if any(
                keyword in error_msg.lower()
                for keyword in ["invalid", "expired", "oauth", "authorization"]
            ):
                results["needs_reauth"].append(
                    f"{integration.page_name} ({integration.workspace.workspace_name})"
                )
                logger.error(
                    f"🚨 Re-authorization needed for {integration.page_name}: {error_msg}"
                )

                # Mark integration as needing attention
                integration.status = "error"
                integration.save(update_fields=["status", "updated_at"])
            else:
                logger.error(
                    f"❌ Unexpected error refreshing {integration.page_name}: {error_msg}"
                )

    logger.info(f"""
    🔄 Meta Token Refresh Summary:
    ✅ Successfully refreshed: {results["refreshed_successfully"]}
    ❌ Failed to refresh: {results["failed_refresh"]}
    🚨 Need re-authorization: {len(results["needs_reauth"])}
    """)

    return results


@shared_task(bind=True)
def cleanup_invalid_google_connections(self):
    """
    Clean up Google Calendar connections that are truly invalid.

    We DO NOT delete just because the access token is expired (normal ~1h TTL).
    We only delete when there is no refresh token, or a refresh attempt returns
    a permanent error (e.g., invalid_grant/authorization revoked).
    """
    from core.models import GoogleCalendar
    from django.conf import settings
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    import logging

    logger = logging.getLogger(__name__)

    calendars = GoogleCalendar.objects.select_related('calendar').all()
    results = {
        "checked": calendars.count(),
        "refreshed": 0,
        "deleted": 0,
        "errors": 0,
        "deleted_accounts": [],
    }

    for gc in calendars:
        try:
            # No refresh token → cannot keep this connection
            if not (gc.refresh_token and gc.refresh_token.strip()):
                name = gc.calendar.name if gc.calendar else "Unknown"
                email = gc.account_email
                if gc.calendar:
                    gc.calendar.delete()
                results["deleted"] += 1
                results["deleted_accounts"].append(email)
                logger.info(f"🗑️ Deleted Google calendar without refresh token: {name} ({email})")
                continue

            # Try a non-intrusive refresh; if it fails with permanent error → delete
            credentials = Credentials(
                token=gc.access_token,
                refresh_token=gc.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                scopes=gc.scopes or settings.GOOGLE_SCOPES,
            )
            try:
                credentials.refresh(Request())
                # Update tokens if changed
                gc.access_token = credentials.token
                try:
                    gc.token_expires_at = credentials.expiry  # may be naive
                except Exception:
                    pass
                gc.save(update_fields=["access_token", "token_expires_at", "updated_at"])
                results["refreshed"] += 1
            except Exception as exc:
                # Permanent invalidation keywords
                msg = str(exc).lower()
                if any(k in msg for k in ["invalid_grant", "unauthorized", "revoked", "invalid_request"]):
                    name = gc.calendar.name if gc.calendar else "Unknown"
                    email = gc.account_email
                    if gc.calendar:
                        gc.calendar.delete()
                    results["deleted"] += 1
                    results["deleted_accounts"].append(email)
                    logger.info(f"🗑️ Deleted revoked Google calendar: {name} ({email}) → {exc}")
                else:
                    results["errors"] += 1
                    logger.warning(f"⚠️ Could not refresh Google token for {gc.account_email}: {exc}")

        except Exception as exc:
            results["errors"] += 1
            logger.error(f"❌ cleanup_invalid_google_connections failed for {gc.account_email}: {exc}")

    logger.info(f"🧹 Google cleanup summary: {results}")
    return results


@shared_task(bind=True)
def cleanup_invalid_outlook_connections(self):
    """
    Clean up Outlook connections only when truly invalid.

    We do not delete merely because the access token is expired; we delete when
    no refresh token exists or refresh fails with a permanent error.
    """
    from core.models import OutlookCalendar
    from core.services.outlook_calendar import OutlookCalendarService
    import logging

    logger = logging.getLogger(__name__)

    calendars = OutlookCalendar.objects.select_related('calendar').all()
    results = {"checked": calendars.count(), "refreshed": 0, "deleted": 0, "errors": 0, "deleted_accounts": []}

    for oc in calendars:
        try:
            if not (oc.refresh_token and oc.refresh_token.strip()):
                name = oc.calendar.name if oc.calendar else "Unknown"
                email = oc.primary_email
                if oc.calendar:
                    oc.calendar.delete()
                results["deleted"] += 1
                results["deleted_accounts"].append(email)
                logger.info(f"🗑️ Deleted Outlook calendar without refresh token: {name} ({email})")
                continue

            try:
                service = OutlookCalendarService()
                token = service.refresh_tokens(oc.refresh_token)
                oc.access_token = token.get('access_token')
                if token.get('refresh_token'):
                    oc.refresh_token = token.get('refresh_token')
                from django.utils import timezone
                oc.token_expires_at = timezone.now() + timedelta(seconds=int(token.get('expires_in', 3600)))
                oc.save(update_fields=['access_token', 'refresh_token', 'token_expires_at', 'updated_at'])
                results["refreshed"] += 1
            except Exception as exc:
                msg = str(exc).lower()
                if any(k in msg for k in ["invalid_grant", "unauthorized", "refresh_token", "authorization"]):
                    name = oc.calendar.name if oc.calendar else "Unknown"
                    email = oc.primary_email
                    if oc.calendar:
                        oc.calendar.delete()
                    results["deleted"] += 1
                    results["deleted_accounts"].append(email)
                    logger.info(f"🗑️ Deleted revoked Outlook calendar: {name} ({email}) → {exc}")
                else:
                    results["errors"] += 1
                    logger.warning(f"⚠️ Could not refresh Outlook token for {oc.primary_email}: {exc}")

        except Exception as exc:
            results["errors"] += 1
            logger.error(f"❌ cleanup_invalid_outlook_connections failed for {oc.primary_email}: {exc}")

    logger.info(f"🧹 Outlook cleanup summary: {results}")
    return results


@shared_task(bind=True)
def cleanup_invalid_meta_integrations(self):
    """
    Clean up invalid or expired Meta integrations.
    Deletes integrations that can no longer be refreshed.

    Runs daily at midnight.
    """
    from core.models import MetaIntegration, MetaLeadForm
    from django.utils import timezone
    from django.db.models import Q
    import logging

    logger = logging.getLogger(__name__)

    now = timezone.now()

    # Find invalid integrations
    invalid_integrations = MetaIntegration.objects.filter(
        Q(access_token_expires_at__lt=now)  # Expired tokens
        | Q(status__in=["error", "invalid", "inactive"])  # Error status
    )

    results = {"total_deleted": 0, "deleted_integrations": [], "deleted_lead_forms": []}

    logger.info(
        f"🧹 Starting cleanup of {invalid_integrations.count()} invalid Meta integrations"
    )

    for integration in invalid_integrations:
        try:
            # Find and delete associated lead forms
            lead_forms = MetaLeadForm.objects.filter(meta_integration=integration)
            for form in lead_forms:
                form_name = form.name
                form.delete()
                results["deleted_lead_forms"].append(form_name)
                logger.info(f"🗑️ Deleted lead form: {form_name}")

            # Delete the integration
            integration_name = (
                f"{integration.page_name} ({integration.workspace.workspace_name})"
            )
            integration.delete()
            results["deleted_integrations"].append(integration_name)
            results["total_deleted"] += 1

            logger.info(f"🗑️ Deleted Meta integration: {integration_name}")

        except Exception as e:
            logger.error(
                f"❌ Error deleting integration {integration.page_name}: {str(e)}"
            )

    logger.info(f"""
    🧹 Meta Cleanup Summary:
    🗑️ Deleted integrations: {results["total_deleted"]}
    📝 Deleted lead forms: {len(results["deleted_lead_forms"])}
    """)

    return results


# ─────────────────────────────
# Meta Lead Form Sync Tasks
# ─────────────────────────────
@shared_task(bind=True, name="core.tasks.sync_meta_lead_forms")
def sync_meta_lead_forms(self, integration_id):
    """
    Background task to sync lead forms from Meta with custom variables extraction

    This task is triggered after OAuth callback to:
    1. Fetch all lead forms from Meta API
    2. Create/update MetaLeadForm records
    3. Auto-create LeadFunnel for each new form
    4. Extract custom variables from form questions
    5. Return comprehensive summary of operations

    Uses the MetaIntegrationService.sync_integration_forms_with_variables method
    for consistent sync logic across all Meta sync operations.
    """
    from core.models import MetaIntegration
    from core.services.meta_integration import MetaIntegrationService
    from django.db import transaction

    logger.info(f"Starting sync_meta_lead_forms for integration {integration_id}")

    try:
        # Get integration with lock to prevent concurrent modifications
        with transaction.atomic():
            integration = MetaIntegration.objects.select_for_update().get(
                id=integration_id
            )

            if integration.status != "active":
                logger.warning(
                    f"Integration {integration_id} is not active, skipping sync"
                )
                return {
                    "success": False,
                    "reason": "integration_not_active",
                    "integration_id": str(integration_id),
                }

            # Use the comprehensive sync method from service
            meta_service = MetaIntegrationService()
            result = meta_service.sync_integration_forms_with_variables(integration)
            
            logger.info(f"Sync completed for integration {integration_id}: {result}")
            return result

    except MetaIntegration.DoesNotExist:
        logger.error(f"Integration {integration_id} not found")
        return {
            "success": False,
            "error": "integration_not_found",
            "integration_id": str(integration_id),
        }
    except Exception as e:
        logger.error(f"Unexpected error in sync_meta_lead_forms: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "integration_id": str(integration_id),
        }


@shared_task(bind=True, name="core.tasks.daily_meta_sync")
def daily_meta_sync(self):
    """
    Daily task to keep all Meta integrations up to date with custom variables extraction
    Runs at midnight to sync all active integrations

    For each active integration:
    - Fetch all forms from Meta API
    - Create/update MetaLeadForm and LeadFunnel records
    - Extract custom variables from form questions
    - Update form names if changed
    - Deactivate forms that no longer exist on Meta

    Uses the MetaIntegrationService.sync_integration_forms_with_variables method
    for consistent sync logic with the OAuth callback sync.
    """
    from core.models import MetaIntegration
    from core.services.meta_integration import MetaIntegrationService
    from django.utils import timezone
    from django.db import transaction

    logger.info("Starting daily Meta sync task")

    # Get all active integrations
    active_integrations = MetaIntegration.objects.filter(
        status="active", access_token_expires_at__gt=timezone.now()
    )

    results = {
        "total_integrations": active_integrations.count(),
        "successful_syncs": 0,
        "failed_syncs": 0,
        "total_forms_processed": 0,
        "total_variables_extracted": 0,
        "integrations": [],
        "timestamp": timezone.now().isoformat(),
    }

    meta_service = MetaIntegrationService()

    for integration in active_integrations:
        try:
            with transaction.atomic():
                # Use the comprehensive sync method from service
                integration_result = meta_service.sync_integration_forms_with_variables(integration)
                
                if integration_result.get('success'):
                    results["successful_syncs"] += 1
                    results["total_forms_processed"] += integration_result.get('total_forms', 0)
                    results["total_variables_extracted"] += integration_result.get('variables_extracted', 0)
                    
                    logger.info(
                        f"Daily sync successful for integration {integration.id}: "
                        f"{integration_result.get('total_forms', 0)} forms, "
                        f"{integration_result.get('variables_extracted', 0)} variable extractions"
                    )
                else:
                    results["failed_syncs"] += 1
                    logger.error(f"Daily sync failed for integration {integration.id}: {integration_result.get('error', 'Unknown error')}")
                
                results["integrations"].append(integration_result)

        except Exception as e:
            logger.error(
                f"Daily sync failed for integration {integration.id}: {str(e)}"
            )
            results["failed_syncs"] += 1
            results["integrations"].append({
                "success": False,
                "integration_id": str(integration.id),
                "workspace": integration.workspace.workspace_name,
                "error": str(e)
            })

    logger.info(
        f"Daily Meta sync completed: {results['successful_syncs']}/{results['total_integrations']} integrations successful, "
        f"{results['total_forms_processed']} forms processed, "
        f"{results['total_variables_extracted']} variable extractions"
    )
    return results
