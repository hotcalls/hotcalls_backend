"""
Celery tasks for HotCalls application.
"""
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from django.db.models import Q, Case, When, IntegerField
from rest_framework.authtoken.models import Token


logger = logging.getLogger(__name__)


@shared_task(bind=True)
def hello_world_test(self):
    """
    Simple test task to verify celery workers are processing tasks.
    
    🧪 Test Task:
    - Logs a hello world message
    - Returns timestamp and worker info
    - Useful for debugging celery setup
    """
    try:
        worker_name = self.request.hostname
        timestamp = timezone.now().isoformat()
        
        logger.info(f"🌍 Hello World from Celery worker: {worker_name} at {timestamp}")
        
        return {
            'message': 'Hello World from Celery!',
            'worker': worker_name,
            'timestamp': timestamp,
            'task_id': self.request.id
        }
        
    except Exception as e:
        logger.error(f"❌ Hello world task failed: {str(e)}")
        return {
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def cleanup_expired_tokens(self):
    """
    Clean up authentication tokens older than 24 hours.
    
    🔐 Security Task:
    - Finds all tokens created more than 24 hours ago
    - Deletes expired tokens from database
    - Forces users to re-login after 24 hours
    - Improves security by limiting token lifetime
    
    📊 Returns count of deleted tokens.
    Recommended to run daily.
    """
    try:
        # Calculate expiration threshold (24 hours ago)
        expiration_threshold = timezone.now() - timedelta(hours=24)
        
        logger.info(f"🔑 Starting token cleanup - removing tokens older than {expiration_threshold}")
        
        # Find expired tokens
        expired_tokens = Token.objects.filter(created__lt=expiration_threshold)
        expired_count = expired_tokens.count()
        
        if expired_count == 0:
            logger.info("✅ No expired tokens found - cleanup complete")
            return {
                'deleted_tokens': 0,
                'message': 'No expired tokens found',
                'timestamp': timezone.now().isoformat(),
                'expiration_threshold': expiration_threshold.isoformat()
            }
        
        # Delete expired tokens
        expired_tokens.delete()
        
        logger.info(f"🗑️ Successfully deleted {expired_count} expired authentication tokens")
        
        return {
            'deleted_tokens': expired_count,
            'message': f'Successfully deleted {expired_count} expired tokens',
            'timestamp': timezone.now().isoformat(),
            'expiration_threshold': expiration_threshold.isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Token cleanup failed: {str(e)}")
        
        # Don't retry automatically as this is a cleanup task
        return {
            'deleted_tokens': 0,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def trigger_call(self, call_task_id):
    """
    Trigger an individual call for a CallTask.
    
    🎯 PURE RESPONSIBILITY: Status management ONLY
    - Updates CallTask status to IN_PROGRESS
    - Calls initiate_call_from_task() (which only makes the call)
    - Handles success/failure and updates status accordingly
    - Implements retry logic based on agent's max_retries
    
    Args:
        call_task_id (str): UUID of the CallTask to process
        
    Returns:
        dict: Task result with success status and details
    """
    from core.models import CallTask, CallStatus
    from core.utils.livekit_calls import initiate_call_from_task
    
    try:
        # Get the call task
        try:
            call_task = CallTask.objects.get(id=call_task_id)
        except CallTask.DoesNotExist:
            logger.error(f"❌ CallTask {call_task_id} not found")
            return {
                'success': False,
                'error': 'CallTask not found',
                'call_task_id': call_task_id
            }
        
        # 🔒 ATOMIC CRITICAL SAFETY CHECKS - Lock task and validate atomically
        from django.db import transaction
        
        try:
            with transaction.atomic():
                # Re-fetch task with row lock to get fresh data and prevent race conditions
                call_task = CallTask.objects.select_for_update().get(id=call_task_id)
                
                # FAST FAIL: If task is not CALL_TRIGGERED, another process got it first
                if call_task.status != CallStatus.CALL_TRIGGERED:
                    logger.warning(f"⚠️ Task {call_task_id} status is {call_task.status}, not CALL_TRIGGERED. Another process got it first.")
                    return {
                        'success': False,
                        'call_task_id': call_task_id,
                        'reason': 'task_status_changed',
                        'current_status': call_task.status,
                        'message': f'Task status is {call_task.status}, expected CALL_TRIGGERED'
                    }
                
                # 1. Check concurrency limit atomically
                current_in_progress = CallTask.objects.filter(status=CallStatus.IN_PROGRESS).count()
                concurrency_limit = settings.NUMBER_OF_LIVEKIT_AGENTS * settings.CONCURRENCY_PER_LIVEKIT_AGENT
                
                if current_in_progress >= concurrency_limit:
                    # Concurrency limit reached - set to WAITING atomically
                    call_task.status = CallStatus.WAITING
                    call_task.save(update_fields=['status', 'updated_at'])
                    
                    logger.warning(f"⏸️ Concurrency limit reached ({current_in_progress}/{concurrency_limit}). Task {call_task_id} set to WAITING")
                    return {
                        'success': False,
                        'call_task_id': call_task_id,
                        'reason': 'concurrency_limit_reached',
                        'current_in_progress': current_in_progress,
                        'concurrency_limit': concurrency_limit,
                        'message': 'Concurrency limit reached, task set to WAITING'
                    }
                
                # 2. Check if another task is already calling this phone number atomically
                phone_in_progress = CallTask.objects.filter(
                    phone=call_task.phone,
                    status=CallStatus.IN_PROGRESS
                ).exclude(id=call_task.id).exists()
                
                if phone_in_progress:
                    # Another task is already calling this phone - set to WAITING atomically
                    call_task.status = CallStatus.WAITING
                    call_task.save(update_fields=['status', 'updated_at'])
                    
                    logger.warning(f"📞 Phone {call_task.phone} already being called. Task {call_task_id} set to WAITING")
                    return {
                        'success': False,
                        'call_task_id': call_task_id,
                        'reason': 'phone_already_in_progress',
                        'phone': call_task.phone,
                        'message': 'Phone number already being called, task set to WAITING'
                    }
                
                # All safety checks passed - ATOMICALLY proceed with call
                call_task.status = CallStatus.IN_PROGRESS
                call_task.save(update_fields=['status', 'updated_at'])
                
        except CallTask.DoesNotExist:
            logger.error(f"❌ CallTask {call_task_id} not found (deleted during processing)")
            return {
                'success': False,
                'error': 'CallTask not found',
                'call_task_id': call_task_id
            }
        
        logger.info(f"📞 Starting call for task {call_task_id} to {call_task.phone} (passed safety checks)")
        
        # ONLY RESPONSIBILITY: Make the call (no status management in livekit_calls)
        call_result = initiate_call_from_task(call_task)
        
        if call_result.get('success', False):
            # Call successful - task completed
            call_task.status = CallStatus.SCHEDULED  # Reset to allow for future scheduling if needed
            call_task.save(update_fields=['status', 'updated_at'])
            
            logger.info(f"✅ Call successfully initiated for task {call_task_id}")
            
            return {
                'success': True,
                'call_task_id': call_task_id,
                'call_result': call_result,
                'message': 'Call initiated successfully'
            }
        else:
            # Call failed - implement retry logic
            agent = call_task.agent
            max_retries = agent.max_retries if agent else 3
            
            if call_task.attempts < max_retries:
                # Increment retry count and set status to RETRY
                call_task.increment_retries(max_retries)
                call_task.status = CallStatus.RETRY
                # Schedule next retry based on agent's retry_interval
                retry_interval = agent.retry_interval if agent else 30
                call_task.next_call = timezone.now() + timedelta(minutes=retry_interval)
                call_task.save(update_fields=['status', 'next_call', 'updated_at'])
                
                logger.warning(f"⚠️ Call failed for task {call_task_id}, scheduled for retry in {retry_interval} minutes")
            else:
                # Max retries reached - set to WAITING
                call_task.status = CallStatus.WAITING
                call_task.save(update_fields=['status', 'updated_at'])
                
                logger.error(f"❌ Call failed for task {call_task_id}, max retries ({max_retries}) reached")
            
            return {
                'success': False,
                'call_task_id': call_task_id,
                'call_result': call_result,
                'attempts': call_task.attempts,
                'max_retries': max_retries,
                'message': 'Call failed, retry logic applied'
            }
            
    except Exception as e:
        logger.error(f"❌ Trigger call task failed for {call_task_id}: {str(e)}")
        
        # Try to update task status to RETRY if possible
        try:
            call_task = CallTask.objects.get(id=call_task_id)
            call_task.status = CallStatus.RETRY
            call_task.save(update_fields=['status', 'updated_at'])
        except:
            pass  # Don't fail if we can't update status
        
        return {
            'success': False,
            'error': str(e),
            'call_task_id': call_task_id
        }


@shared_task(bind=True)
def schedule_agent_call(self):
    """
    Periodic task to schedule agent calls based on CallTask queue.
    
    🕐 RUNS EVERY SECOND via Celery Beat
    
    Logic:
    1. Filter CallTasks: next_call < now() AND status != IN_PROGRESS
    2. Order by priority: WAITING > SCHEDULED > RETRY
    3. Count current IN_PROGRESS tasks
    4. Calculate available slots: (agents * concurrency_per_agent) - in_progress
    5. Spawn trigger_call tasks for available slots
    
    Returns:
        dict: Scheduling result with counts and actions taken
    """
    from core.models import CallTask, CallStatus
    
    try:
        now = timezone.now()
        
        # Count current IN_PROGRESS calls
        in_progress_count = CallTask.objects.filter(status=CallStatus.IN_PROGRESS).count()
        
        # Calculate concurrency limit
        concurrency_limit = settings.NUMBER_OF_LIVEKIT_AGENTS * settings.CONCURRENCY_PER_LIVEKIT_AGENT
        
        # Calculate available slots
        num_to_schedule = concurrency_limit - in_progress_count
        
        logger.info(f"📊 Scheduling check: {in_progress_count} in progress, {concurrency_limit} limit, {num_to_schedule} slots available")
        
        if num_to_schedule <= 0:
            return {
                'success': True,
                'scheduled_count': 0,
                'in_progress_count': in_progress_count,
                'concurrency_limit': concurrency_limit,
                'message': 'No available slots for new calls'
            }
        
        # Filter tasks ready for calling (excluding IN_PROGRESS and CALL_TRIGGERED)
        # 🔒 SKIP LOCKED: Prevent multiple schedulers from picking same tasks
        ready_tasks = CallTask.objects.select_for_update(skip_locked=True).filter(
            next_call__lt=now
        ).exclude(
            status__in=[CallStatus.IN_PROGRESS, CallStatus.CALL_TRIGGERED]
        ).annotate(
            # Priority ordering: WAITING=1, SCHEDULED=2, RETRY=3
            priority=Case(
                When(status=CallStatus.WAITING, then=1),
                When(status=CallStatus.SCHEDULED, then=2),
                When(status=CallStatus.RETRY, then=3),
                default=4,
                output_field=IntegerField()
            )
        ).order_by('priority', 'next_call')[:num_to_schedule]
        
        scheduled_count = 0
        scheduled_task_ids = []
        
        # Spawn trigger_call tasks for available slots - ATOMIC TRANSACTION
        from django.db import transaction
        
        for task in ready_tasks:
            try:
                # 🔒 ATOMIC TRANSACTION: Lock row, check status, update status
                with transaction.atomic():
                    # Re-fetch with row lock to prevent race conditions
                    locked_task = CallTask.objects.select_for_update().get(id=task.id)
                    
                    # Double-check status hasn't changed (prevent race condition)
                    if locked_task.status in [CallStatus.IN_PROGRESS, CallStatus.CALL_TRIGGERED]:
                        logger.warning(f"⚠️ Task {task.id} status changed to {locked_task.status}, skipping")
                        continue
                    
                    # ATOMICALLY update status
                    locked_task.status = CallStatus.CALL_TRIGGERED
                    locked_task.save(update_fields=['status', 'updated_at'])
                
                # AFTER transaction commits, spawn async task with ID only
                trigger_call.delay(str(task.id))
                scheduled_count += 1
                scheduled_task_ids.append(str(task.id))
                
                logger.info(f"📞 Scheduled call task {task.id} for {task.phone} (status: CALL_TRIGGERED)")
                
            except CallTask.DoesNotExist:
                logger.warning(f"⚠️ Task {task.id} was deleted, skipping")
                continue
            except Exception as e:
                logger.error(f"❌ Failed to schedule call task {task.id}: {str(e)}")
                continue
        
        logger.info(f"✅ Scheduled {scheduled_count} call tasks out of {num_to_schedule} available slots")
        
        return {
            'success': True,
            'scheduled_count': scheduled_count,
            'scheduled_task_ids': scheduled_task_ids,
            'in_progress_count': in_progress_count,
            'concurrency_limit': concurrency_limit,
            'available_slots': num_to_schedule,
            'timestamp': now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Schedule agent call task failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def cleanup_stuck_call_tasks(self):
    """
    Cleanup task to remove stuck CallTasks that prevent system recovery.
    
    🧹 RUNS EVERY MINUTE
    
    Safety cleanup rules:
    1. Delete CALL_TRIGGERED tasks older than 10 minutes (spawned but never executed)
    2. Delete IN_PROGRESS tasks older than 30 minutes (likely stuck/failed calls)
    
    This prevents accumulated stuck tasks from breaking the call system.
    
    Returns:
        dict: Cleanup result with counts of deleted tasks
    """
    from core.models import CallTask, CallStatus
    
    try:
        now = timezone.now()
        
        # Calculate cleanup thresholds
        call_triggered_threshold = now - timedelta(minutes=10)
        in_progress_threshold = now - timedelta(minutes=30)
        
        # Find CALL_TRIGGERED tasks older than 10 minutes
        # 🔒 LOCK FOR UPDATE: Prevent race conditions during cleanup
        stuck_triggered_tasks = CallTask.objects.select_for_update().filter(
            status=CallStatus.CALL_TRIGGERED,
            updated_at__lt=call_triggered_threshold
        )
        triggered_count = stuck_triggered_tasks.count()
        
        # Find IN_PROGRESS tasks older than 30 minutes  
        # 🔒 LOCK FOR UPDATE: Prevent race conditions during cleanup
        stuck_progress_tasks = CallTask.objects.select_for_update().filter(
            status=CallStatus.IN_PROGRESS,
            updated_at__lt=in_progress_threshold
        )
        progress_count = stuck_progress_tasks.count()
        
        total_to_delete = triggered_count + progress_count
        
        if total_to_delete == 0:
            return {
                'success': True,
                'deleted_triggered': 0,
                'deleted_progress': 0,
                'total_deleted': 0,
                'message': 'No stuck tasks found - cleanup complete',
                'timestamp': now.isoformat()
            }
        
        logger.warning(f"🧹 Cleanup: Found {triggered_count} stuck CALL_TRIGGERED + {progress_count} stuck IN_PROGRESS tasks")
        
        # Log details of tasks being deleted (for debugging)
        if triggered_count > 0:
            triggered_ids = list(stuck_triggered_tasks.values_list('id', flat=True))
            logger.warning(f"🗑️ Deleting CALL_TRIGGERED tasks (>10min): {triggered_ids}")
            
        if progress_count > 0:
            progress_ids = list(stuck_progress_tasks.values_list('id', flat=True))  
            logger.warning(f"🗑️ Deleting IN_PROGRESS tasks (>30min): {progress_ids}")
        
        # HARD DELETE stuck tasks
        stuck_triggered_tasks.delete()
        stuck_progress_tasks.delete()
        
        logger.info(f"✅ Cleanup complete: Deleted {total_to_delete} stuck call tasks ({triggered_count} CALL_TRIGGERED + {progress_count} IN_PROGRESS)")
        
        return {
            'success': True,
            'deleted_triggered': triggered_count,
            'deleted_progress': progress_count,
            'total_deleted': total_to_delete,
            'message': f'Successfully deleted {total_to_delete} stuck tasks',
            'timestamp': now.isoformat(),
            'call_triggered_threshold': call_triggered_threshold.isoformat(),
            'in_progress_threshold': in_progress_threshold.isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Cleanup stuck call tasks failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'deleted_triggered': 0,
            'deleted_progress': 0,
            'total_deleted': 0,
            'timestamp': timezone.now().isoformat()
        }
