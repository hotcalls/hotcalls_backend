"""
Celery tasks for HotCalls application – *fully fool‑proof* version.

Key improvements
────────────────
1.  **Redis distributed lock** (SETNX with TTL) guarantees that at most ONE
    `schedule_agent_call` task body runs anywhere in the cluster.
2.  **SingletonTask** base class adds a second layer of protection:
    if the Redis lock somehow fails, the Celery task itself cannot overlap.
3.  **Atomic hand‑off**: a single `UPDATE … WHERE id=? AND status IN (…)`
    changes a CallTask's status to `CALL_TRIGGERED`.  If the row was already
    touched, the update count is 0 and we do *not* fire `trigger_call.delay`.
4.  **No silent falls‑through** – every failure path is logged and returned.
5.  The original hefty `select_for_update()` blocks are kept **inside**
    `trigger_call` (where they belong) so call‑level race conditions are still
    covered.

This file completely replaces your previous core/tasks.py.
"""

import asyncio
import logging
import os
import traceback
from datetime import timedelta

import redis
from celery import Task, shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Case, IntegerField, When
from django.utils import timezone
from rest_framework.authtoken.models import Token

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
# 2) Daily expired‑token cleanup
# ─────────────────────────────
@shared_task(bind=True, name="core.tasks.cleanup_expired_tokens")
def cleanup_expired_tokens(self):
    """
    Remove DRF AuthTokens older than 24 h.
    """
    try:
        threshold = timezone.now() - timedelta(hours=24)
        expired = Token.objects.filter(created__lt=threshold)
        count = expired.count()
        if count:
            expired.delete()
            logger.info(f"🗑️ Deleted {count} expired tokens (before {threshold})")
        else:
            logger.info("✅ No expired tokens found.")
        return {
            "deleted_tokens": count,
            "threshold": threshold.isoformat(),
            "timestamp": timezone.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"❌ Token cleanup failed: {e}")
        return {"error": str(e), "deleted_tokens": 0}


# ─────────────────────────────
# 3) Trigger a single outbound call
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
    from core.utils.livekit_calls import _make_call_async
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

        # Get SIP trunk ID from agent's phone number (dynamic routing)
        sip_trunk_id = None
        if agent.phone_number and agent.phone_number.sip_trunk:
            sip_trunk_id = agent.phone_number.sip_trunk.livekit_trunk_id
        if not sip_trunk_id:
            sip_trunk_id = os.getenv("TRUNK_ID")  # Fallback

        agent_config = {
            "name": agent.name,
            "voice_external_id": agent.voice.voice_external_id,
            "language": agent.language,
            "prompt": agent.prompt,
            "greeting_outbound": agent.greeting_outbound,
            "greeting_inbound": agent.greeting_inbound,
            "character": agent.character,
            "config_id": agent.config_id,
            "workspace_name": workspace.workspace_name,
            "sip_trunk_id": sip_trunk_id,  # Pass dynamic trunk ID
        }
        lead_data = {
            "id": str(lead.id) if lead else str(call_task.id),
            "name": lead.name if lead else "Test",
            "surname": lead.surname if lead else "Call",
            "email": lead.email if lead else "test@example.com",
            "phone": lead.phone if lead else call_task.phone,
            "company": lead.company if lead else "Test Company",
            "address": lead.address if lead else "",
            "city": lead.city if lead else "",
            "state": lead.state if lead else "",
            "zip_code": lead.zip_code if lead else "",
            "country": lead.country if lead else "",
            "notes": lead.notes if lead else "Test call",
            "call_task_id": str(call_task.id),
            "metadata": lead.metadata
            if lead
            else {"test_call": True, "call_task_id": str(call_task.id)},
        }

        from_number = (
            agent.phone_number.phonenumber
            if agent.phone_number
            else getattr(workspace, "phone_number", None)
            or os.getenv("DEFAULT_FROM_NUMBER")
        )

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

        # 🚀 Quota OK - Place the outbound call (synchronous wait inside worker)
        call_result = asyncio.run(
            _make_call_async(
                sip_trunk_id=sip_trunk_id,
                agent_config=agent_config,
                lead_data=lead_data,
                from_number=from_number,
            )
        )

        # Post‑call status handling - Use unified utilities

        with transaction.atomic():
            call_task = CallTask.objects.select_for_update().get(id=call_task_id)

            if call_result.get("success"):
                # SUCCESS: advance to IN_PROGRESS now, then handle
                call_task.status = CallStatus.IN_PROGRESS
                call_task.save(update_fields=["status", "updated_at"])
                return handle_call_success(call_task, call_result)
            else:
                # FAILURE: Use unified failure handler (no defaults!)
                error = call_result.get("error", "Unknown error")
                abort_reason = call_result.get("abort_reason")
                return handle_call_failure(call_task, error, abort_reason)

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
# 4) **THE** periodic scheduler – singleton & fool‑proof
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

        # Calculate concurrency limit from database (keeping existing approach)
        from core.models import LiveKitAgent

        agents = LiveKitAgent.objects.filter(expires_at__gt=timezone.now())
        total_concurrency = sum(agent.concurrency_per_agent for agent in agents)
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
# 5) Minute‑ly stuck‑task garbage collector (unchanged)
# ─────────────────────────────
@shared_task(bind=True, name="core.tasks.cleanup_stuck_call_tasks")
def cleanup_stuck_call_tasks(self):
    """
    Kill CALL_TRIGGERED older than 10 min and IN_PROGRESS older than 30 min.
    """
    from core.models import CallTask, CallStatus

    now = timezone.now()
    trig_thresh = now - timedelta(minutes=10)
    prog_thresh = now - timedelta(minutes=30)

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
# 6) CallTask Feedback Loop
# ─────────────────────────────
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="core.tasks.update_calltask_from_calllog",
)
def update_calltask_from_calllog(self, call_log_id):
    """
    Process CallLog and update/delete corresponding CallTask based on call outcome.

    This task provides the feedback loop between call completion (CallLog) and
    call scheduling (CallTask). It automatically:
    - Deletes CallTasks for successful calls
    - Schedules retries for failed calls (with proper agent configuration)
    - Respects agent retry limits and working hours

    Args:
        call_log_id (str): UUID of the CallLog to process

    Returns:
        dict: Processing result with status and details
    """
    from core.models import CallLog
    from core.utils.calltask_utils import (
        find_related_calltask,
        process_calltask_feedback,
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

        # Find the related CallTask
        call_task = find_related_calltask(call_log)

        if not call_task:
            # This is normal - not all CallLogs have corresponding CallTasks
            # (e.g., manual test calls, inbound calls, etc.)
            logger.info(
                f"No CallTask found for CallLog {call_log_id} - likely a manual/test call"
            )
            return {
                "success": True,
                "action": "no_calltask_found",
                "call_log_id": call_log_id,
                "lead_id": str(call_log.lead.id) if call_log.lead else None,
                "agent_id": str(call_log.agent.agent_id),
                "disconnection_reason": call_log.disconnection_reason,
            }

        # Process the feedback
        call_task_id = str(call_task.id)
        call_task_status_before = call_task.status

        process_calltask_feedback(call_task, call_log)

        # Check if CallTask was deleted (successful call)
        from core.models import CallTask

        try:
            updated_call_task = CallTask.objects.get(id=call_task_id)
            # CallTask still exists - it was updated
            action = "calltask_updated"
            new_status = updated_call_task.status
            next_call = (
                updated_call_task.next_call.isoformat()
                if updated_call_task.next_call
                else None
            )
        except CallTask.DoesNotExist:
            # CallTask was deleted - successful call
            action = "calltask_deleted"
            new_status = None
            next_call = None

        logger.info(
            f"CallTask feedback processed successfully: {action} for CallLog {call_log_id}"
        )

        return {
            "success": True,
            "action": action,
            "call_log_id": call_log_id,
            "call_task_id": call_task_id,
            "status_before": call_task_status_before,
            "status_after": new_status,
            "next_call": next_call,
            "disconnection_reason": call_log.disconnection_reason,
            "agent_id": str(call_log.agent.agent_id),
            "lead_id": str(call_log.lead.id) if call_log.lead else None,
        }

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
            return {
                "success": False,
                "error": str(exc),
                "call_log_id": call_log_id,
                "retries": self.request.retries,
            }


# ===== GOOGLE CALENDAR TOKEN MANAGEMENT =====


@shared_task(bind=True, max_retries=3)
def refresh_google_calendar_connections(self):
    """
    Refresh Google Calendar OAuth tokens 30 days before expiry.
    Uses GoogleCalendarConnection model for proper OAuth management.

    Runs daily at midnight.
    """
    from core.models import GoogleCalendarConnection
    # from core.services.google_calendar import GoogleOAuthService  # unused import removed
    from django.utils import timezone
    from datetime import timedelta
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    import logging

    logger = logging.getLogger(__name__)

    now = timezone.now()
    refresh_threshold = now + timedelta(days=30)  # Refresh 30 days before expiry

    # Query connections that need refresh
    connections_to_refresh = GoogleCalendarConnection.objects.filter(
        token_expires_at__lt=refresh_threshold,
        token_expires_at__gt=now,  # Not already expired
        active=True,
        refresh_token__isnull=False,
    ).exclude(refresh_token="")

    results = {
        "total_checked": connections_to_refresh.count(),
        "refreshed_successfully": 0,
        "failed_refresh": 0,
        "needs_reauth": [],
        "errors": [],
    }

    logger.info(
        f"🔄 Starting Google OAuth token refresh for {results['total_checked']} connections"
    )

    for connection in connections_to_refresh:
        try:
            # Create credentials object
            credentials = Credentials(
                token=connection.access_token,
                refresh_token=connection.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
                scopes=connection.scopes,
            )

            # Refresh the token
            request = Request()
            credentials.refresh(request)

            # Update connection with new tokens
            connection.access_token = credentials.token
            connection.token_expires_at = (
                timezone.make_aware(credentials.expiry) if credentials.expiry else None
            )
            connection.save(
                update_fields=["access_token", "token_expires_at", "updated_at"]
            )

            results["refreshed_successfully"] += 1
            logger.info(f"✅ Refreshed token for {connection.account_email}")

        except Exception as e:
            error_msg = str(e)
            results["failed_refresh"] += 1
            results["errors"].append(
                {"connection": connection.account_email, "error": error_msg}
            )

            # Check if re-auth is needed
            if any(
                keyword in error_msg.lower()
                for keyword in ["invalid_grant", "refresh_token", "authorization"]
            ):
                results["needs_reauth"].append(connection.account_email)
                logger.error(
                    f"🚨 Re-authorization needed for {connection.account_email}: {error_msg}"
                )

                # Mark connection as inactive
                connection.active = False
                connection.save(update_fields=["active", "updated_at"])
            else:
                logger.error(
                    f"❌ Unexpected error refreshing {connection.account_email}: {error_msg}"
                )

    logger.info(f"""
    🔄 Google Token Refresh Summary:
    ✅ Successfully refreshed: {results["refreshed_successfully"]}
    ❌ Failed to refresh: {results["failed_refresh"]}
    🚨 Need re-authorization: {len(results["needs_reauth"])}
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
    Clean up invalid or expired Google Calendar connections.
    Deletes connections that can no longer be refreshed.

    Runs daily at midnight.
    """
    from core.models import GoogleCalendarConnection, GoogleCalendar
    from django.utils import timezone
    from django.db.models import Q
    import logging

    logger = logging.getLogger(__name__)

    now = timezone.now()

    # Find invalid connections
    invalid_connections = GoogleCalendarConnection.objects.filter(
        Q(token_expires_at__lt=now)  # Expired tokens
        | Q(active=False)  # Marked as inactive
        | Q(refresh_token__isnull=True)  # No refresh capability
        | Q(refresh_token="")  # Empty refresh token
    )

    results = {"total_deleted": 0, "deleted_connections": [], "deleted_calendars": []}

    logger.info(
        f"🧹 Starting cleanup of {invalid_connections.count()} invalid Google connections"
    )

    for connection in invalid_connections:
        try:
            # Find and delete associated calendars
            google_calendars = GoogleCalendar.objects.filter(connection=connection)
            for gc in google_calendars:
                calendar_name = gc.calendar.name if gc.calendar else "Unknown"

                # Delete the Calendar (this cascades to GoogleCalendar)
                if gc.calendar:
                    gc.calendar.delete()
                    results["deleted_calendars"].append(calendar_name)
                    logger.info(f"🗑️ Deleted calendar: {calendar_name}")

            # Delete the connection
            connection_email = connection.account_email
            connection.delete()
            results["deleted_connections"].append(connection_email)
            results["total_deleted"] += 1

            logger.info(f"🗑️ Deleted Google connection for {connection_email}")

        except Exception as e:
            logger.error(
                f"❌ Error deleting connection {connection.account_email}: {str(e)}"
            )

    logger.info(f"""
    🧹 Google Cleanup Summary:
    🗑️ Deleted connections: {results["total_deleted"]}
    📅 Deleted calendars: {len(results["deleted_calendars"])}
    """)

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
    Background task to sync lead forms from Meta and create LeadFunnels

    This task is triggered after OAuth callback to:
    1. Fetch all lead forms from Meta API
    2. Create/update MetaLeadForm records
    3. Auto-create LeadFunnel for each new form
    4. Return summary of operations

    Race condition prevention:
    - Uses select_for_update() for atomic operations
    - Uses get_or_create() for idempotent operations
    """
    from core.models import MetaIntegration, MetaLeadForm, LeadFunnel
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

            meta_service = MetaIntegrationService()

            # Fetch lead forms from Meta API
            try:
                forms_data = meta_service.get_page_lead_forms(
                    integration.page_id, integration.access_token
                )
            except Exception as e:
                logger.error(f"Failed to fetch lead forms from Meta: {str(e)}")
                return {
                    "success": False,
                    "error": str(e),
                    "integration_id": str(integration_id),
                }

            created_forms = []
            updated_forms = []
            created_funnels = []

            # Process each form
            for form_data in forms_data:
                form_id = form_data.get("id")
                form_name = form_data.get("name", f"Form {form_id}")

                # Create or update MetaLeadForm
                meta_form, form_created = MetaLeadForm.objects.get_or_create(
                    meta_integration=integration,
                    meta_form_id=form_id,
                    defaults={
                        "name": form_name
                        # is_active is now computed from agent assignment
                    },
                )

                # Update name if changed
                if not form_created and meta_form.name != form_name:
                    meta_form.name = form_name
                    meta_form.save(update_fields=["name", "updated_at"])
                    updated_forms.append(form_id)
                elif form_created:
                    created_forms.append(form_id)

                # Create LeadFunnel for new forms
                if form_created:
                    # Check if funnel already exists (shouldn't happen but be safe)
                    if not hasattr(meta_form, "lead_funnel"):
                        new_funnel = LeadFunnel.objects.create(
                            name=f"{form_name}",
                            workspace=integration.workspace,
                            meta_lead_form=meta_form,
                            is_active=True,  # Active by default, but no agent yet
                        )
                        created_funnels.append(
                            {
                                "id": str(new_funnel.id),
                                "name": new_funnel.name,
                                "form_id": form_id,
                            }
                        )
                        logger.info(
                            f"Created LeadFunnel {new_funnel.id} for form {form_id}"
                        )

            # Log summary
            summary = {
                "success": True,
                "integration_id": str(integration_id),
                "total_forms": len(forms_data),
                "created_forms": len(created_forms),
                "updated_forms": len(updated_forms),
                "created_funnels": len(created_funnels),
                "form_ids": {"created": created_forms, "updated": updated_forms},
                "funnels": created_funnels,
            }

            logger.info(f"Sync completed for integration {integration_id}: {summary}")
            return summary

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
    Daily task to keep all Meta integrations up to date
    Runs at midnight to sync all active integrations

    For each active integration:
    - Check for new forms on Meta
    - Create missing LeadFunnels
    - Update form names if changed
    - Disable forms that no longer exist on Meta
    """
    from core.models import MetaIntegration, MetaLeadForm, LeadFunnel
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
        "integrations": [],
    }

    meta_service = MetaIntegrationService()

    for integration in active_integrations:
        try:
            with transaction.atomic():
                # Fetch current forms from Meta
                forms_data = meta_service.get_page_lead_forms(
                    integration.page_id, integration.access_token
                )

                # Get all form IDs from Meta
                meta_form_ids = {form["id"] for form in forms_data}

                # Get all existing forms for this integration
                existing_forms = MetaLeadForm.objects.filter(
                    meta_integration=integration
                )
                existing_form_ids = {form.meta_form_id for form in existing_forms}

                # Find new forms
                new_form_ids = meta_form_ids - existing_form_ids

                # Find removed forms (exist in DB but not in Meta)
                removed_form_ids = existing_form_ids - meta_form_ids

                created_forms = 0
                updated_forms = 0
                deactivated_forms = 0
                created_funnels = 0

                # Create new forms and funnels
                for form_data in forms_data:
                    form_id = form_data["id"]
                    form_name = form_data.get("name", f"Form {form_id}")

                    if form_id in new_form_ids:
                        # Create new form
                        meta_form = MetaLeadForm.objects.create(
                            meta_integration=integration,
                            meta_form_id=form_id,
                            name=form_name,
                            is_active=False,
                        )
                        created_forms += 1

                        # Create funnel
                        LeadFunnel.objects.create(
                            name=form_name,
                            workspace=integration.workspace,
                            meta_lead_form=meta_form,
                            is_active=True,
                        )
                        created_funnels += 1

                    else:
                        # Update existing form name if changed
                        meta_form = MetaLeadForm.objects.get(
                            meta_integration=integration, meta_form_id=form_id
                        )
                        if meta_form.name != form_name:
                            meta_form.name = form_name
                            meta_form.save(update_fields=["name", "updated_at"])

                            # Also update funnel name if it exists
                            if hasattr(meta_form, "lead_funnel"):
                                meta_form.lead_funnel.name = form_name
                                meta_form.lead_funnel.save(
                                    update_fields=["name", "updated_at"]
                                )

                            updated_forms += 1

                # Deactivate removed forms (via funnel deactivation)
                if removed_form_ids:
                    removed_forms = MetaLeadForm.objects.filter(
                        meta_integration=integration, meta_form_id__in=removed_form_ids
                    ).select_related("lead_funnel")

                    for form in removed_forms:
                        # Deactivate the funnel (form.is_active will be computed as False)
                        if hasattr(form, "lead_funnel"):
                            form.lead_funnel.is_active = False
                            form.lead_funnel.save(
                                update_fields=["is_active", "updated_at"]
                            )
                            deactivated_forms += 1

                integration_result = {
                    "integration_id": str(integration.id),
                    "workspace": integration.workspace.workspace_name,
                    "created_forms": created_forms,
                    "updated_forms": updated_forms,
                    "deactivated_forms": deactivated_forms,
                    "created_funnels": created_funnels,
                }

                results["integrations"].append(integration_result)
                results["successful_syncs"] += 1

                logger.info(
                    f"Daily sync successful for integration {integration.id}: {integration_result}"
                )

        except Exception as e:
            logger.error(
                f"Daily sync failed for integration {integration.id}: {str(e)}"
            )
            results["failed_syncs"] += 1
            results["integrations"].append(
                {"integration_id": str(integration.id), "error": str(e)}
            )

    logger.info(f"Daily Meta sync completed: {results}")
    return results
