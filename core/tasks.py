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
        
        # CRITICAL SAFETY CHECKS before proceeding with call
        
        # 1. Check concurrency limit (other trigger_call tasks might have started)
        current_in_progress = CallTask.objects.filter(status=CallStatus.IN_PROGRESS).count()
        concurrency_limit = settings.NUMBER_OF_LIVEKIT_AGENTS * settings.CONCURRENCY_PER_LIVEKIT_AGENT
        
        if current_in_progress >= concurrency_limit:
            # Concurrency limit reached - set to WAITING
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
        
        # 2. Check if another task is already calling this phone number
        phone_in_progress = CallTask.objects.filter(
            phone=call_task.phone,
            status=CallStatus.IN_PROGRESS
        ).exclude(id=call_task.id).exists()
        
        if phone_in_progress:
            # Another task is already calling this phone - set to WAITING
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
        
        # All safety checks passed - proceed with call
        call_task.status = CallStatus.IN_PROGRESS
        call_task.save(update_fields=['status', 'updated_at'])
        
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
        
        # Filter tasks ready for calling (excluding IN_PROGRESS)
        ready_tasks = CallTask.objects.filter(
            next_call__lt=now
        ).exclude(
            status=CallStatus.IN_PROGRESS
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
        
        # Spawn trigger_call tasks for available slots
        for task in ready_tasks:
            try:
                # Spawn async trigger_call task
                trigger_call.delay(str(task.id))
                scheduled_count += 1
                scheduled_task_ids.append(str(task.id))
                
                logger.info(f"📞 Scheduled call task {task.id} for {task.phone}")
                
            except Exception as e:
                logger.error(f"❌ Failed to schedule call task {task.id}: {str(e)}")
        
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
