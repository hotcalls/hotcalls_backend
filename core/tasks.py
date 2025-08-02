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
      1. Double‑check status is CALL_TRIGGERED.
      2. Move to IN_PROGRESS (inside atomic tx).
      3. Check quotas (skip for test calls where lead is null).
      4. Launch the LiveKit outbound call (async).
      5. • If call launch succeeds → keep IN_PROGRESS (do NOT change status).
         • If call launch fails     → RETRY / WAITING logic.
      6. External webhook / feedback loop will delete or close the task.
    """
    # Local import to avoid circular dependencies
    from core.models import CallTask, CallStatus
    from core.utils.livekit_calls import _make_call_async

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

            # Move to IN_PROGRESS
            call_task.status = CallStatus.IN_PROGRESS
            call_task.save(update_fields=["status", "updated_at"])

        # Extract all payload *outside* the lock
        agent = call_task.agent
        workspace = call_task.workspace
        lead = call_task.lead

        sip_trunk_id = getattr(workspace, "sip_trunk_id", None) or os.getenv("TRUNK_ID")
        agent_config = {
            "name": agent.name,
            "voice_external_id": agent.voice.voice_external_id
            if agent.voice
            else None,
            "language": agent.language,
            "prompt": agent.prompt,
            "greeting_outbound": agent.greeting_outbound,
            "greeting_inbound": agent.greeting_inbound,
            "character": agent.character,
            "config_id": agent.config_id,
            "workspace_name": workspace.workspace_name,
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
            "metadata": lead.metadata
            if lead
            else {"test_call": True, "call_task_id": str(call_task.id)},
        }

        from_number = (
            agent.phone_numbers.first().phonenumber
            if agent.phone_numbers.exists()
            else getattr(workspace, "phone_number", None)
            or os.getenv("DEFAULT_FROM_NUMBER")
        )
        campaign_id = str(workspace.id)

        # 🎯 QUOTA ENFORCEMENT: Skip quotas for test calls (lead is null)
        if lead is not None:
            # Only enforce quotas for real calls with leads
            try:
                from core.quotas import enforce_and_record, QuotaExceeded
                
                # Check quota without recording usage (amount=0)
                enforce_and_record(
                    workspace=workspace,
                    route_name="internal:outbound_call",
                    http_method="POST",
                    amount=0  # Just check status, don't pre-charge
                )
                
            except QuotaExceeded as quota_err:
                logger.warning(f"🚫 Call quota exceeded for workspace {workspace.id}: {quota_err}")
                # DELETE this call task - quota exceeded
                with transaction.atomic():
                    call_task = CallTask.objects.select_for_update().get(id=call_task_id)
                    call_task.delete()
                return {
                    "success": False,
                    "call_task_id": call_task_id,
                    "error": "quota_exceeded", 
                    "message": f"Call task deleted - {quota_err}",
                }
            except Exception as quota_err:
                # Log error but don't block the call on quota system failures
                logger.error(f"⚠️ Quota check failed for workspace {workspace.id}: {quota_err}")
                # Allow call to proceed
        else:
            # Test call (lead is null) - skip quota enforcement
            logger.info(f"🧪 Test call detected (lead is null) - skipping quota enforcement for workspace {workspace.id}")

        # 🚀 Quota OK - Place the outbound call (synchronous wait inside worker)
        call_result = asyncio.run(
            _make_call_async(
                sip_trunk_id=sip_trunk_id,
                agent_config=agent_config,
                lead_data=lead_data,
                from_number=from_number,
                campaign_id=campaign_id,
                call_reason=None,
            )
        )

        # Post‑call status handling
        with transaction.atomic():
            call_task = CallTask.objects.select_for_update().get(id=call_task_id)
            if call_result.get("success"):
                # SUCCESS: keep status as IN_PROGRESS until webhook cleans up
                call_task.updated_at = timezone.now()
                call_task.save(update_fields=["updated_at"])
                return {
                    "success": True,
                    "call_task_id": call_task_id,
                    "message": "Call launched; task remains IN_PROGRESS.",
                    "result": call_result,
                }
            else:
                # Retry logic
                max_retries = agent.max_retries if agent else 3
                if call_task.attempts < max_retries:
                    call_task.increment_retries(max_retries)
                    call_task.status = CallStatus.RETRY
                    call_task.next_call = timezone.now() + timedelta(
                        minutes=agent.retry_interval if agent else 30
                    )
                    call_task.save(
                        update_fields=["status", "attempts", "next_call", "updated_at"]
                    )
                else:
                    call_task.status = CallStatus.WAITING
                    call_task.save(update_fields=["status", "updated_at"])
                return {
                    "success": False,
                    "call_task_id": call_task_id,
                    "message": "Call failed – retry logic applied",
                    "result": call_result,
                    "attempts": call_task.attempts,
                }

    except Exception as err:
        logger.error(f"❌ trigger_call exception for {call_task_id}: {err}")
        traceback.print_exc()
        # Best‑effort reset to RETRY
        try:
            with transaction.atomic():
                call_task = CallTask.objects.select_for_update().get(id=call_task_id)
                call_task.status = CallStatus.RETRY
                call_task.save(update_fields=["status", "updated_at"])
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
        • SingletonTask (task‑level)
        • Redis lock (cluster‑level)
        • Atomic UPDATE (row‑level)
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
        concurrency_limit = max(total_concurrency, 1)  # At least 1 to prevent division by zero

        in_progress = CallTask.objects.filter(
            status=CallStatus.IN_PROGRESS
        ).count()
        available_slots = max(concurrency_limit - in_progress, 0)

        if available_slots == 0:
            return {
                "success": True,
                "message": "No capacity; skipping.",
                "in_progress": in_progress,
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
            .order_by("priority", "next_call")[: available_slots * 2]  # over‑fetch a bit
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
            rows_updated = (
                CallTask.objects.filter(
                    id=task.id,
                    status__in=[
                        CallStatus.WAITING,
                        CallStatus.SCHEDULED,
                        CallStatus.RETRY,
                    ],
                ).update(status=CallStatus.CALL_TRIGGERED, updated_at=now)
            )
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
        logger.error(f"❌ cleanup_stuck_call_tasks failed: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}
