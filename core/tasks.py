"""
Celery tasks for HotCalls application.
"""
import asyncio
import logging
import os
import traceback
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from django.db.models import Case, When, IntegerField
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
    - Extracts all data within atomic transaction 
    - Calls _make_call_async() directly with pure data (zero DB coupling)
    - Handles success/failure and updates status accordingly
    - Implements retry logic based on agent's max_retries
    
    Args:
        call_task_id (str): UUID of the CallTask to process
        
    Returns:
        dict: Task result with success status and details
    """
    from core.models import CallTask, CallStatus
    
    
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
                # Calculate concurrency limit from database
                from core.models import LiveKitAgent
                agents = LiveKitAgent.objects.filter(expires_at__gt=timezone.now())
                total_concurrency = sum(agent.concurrency_per_agent for agent in agents)
                concurrency_limit = max(total_concurrency, 1)  # At least 1 to prevent division by zero
                
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
                
                # 📦 EXTRACT ALL DATA within transaction (explicit DB access - zero coupling)
                agent = call_task.agent
                workspace = call_task.workspace
                lead = call_task.lead
                
                sip_trunk_id = getattr(workspace, 'sip_trunk_id', None) or os.getenv('TRUNK_ID')
                agent_config = {
                    'name': agent.name,
                    'voice_external_id': agent.voice.voice_external_id if agent.voice else None,
                    'language': agent.language,
                    'prompt': agent.prompt,
                    'greeting_outbound': agent.greeting_outbound,
                    'greeting_inbound': agent.greeting_inbound,
                    'character': agent.character,
                    'config_id': agent.config_id,
                    'workspace_name': workspace.workspace_name,
                }
                
                lead_data = {
                    'id': str(lead.id) if lead else str(call_task.id),
                    'name': lead.name if lead else 'Test',
                    'surname': lead.surname if lead else 'Call',
                    'email': lead.email if lead else 'test@example.com',
                    'phone': lead.phone if lead else call_task.phone,
                    'company': lead.company if lead else 'Test Company',
                    'address': lead.address if lead else '',
                    'city': lead.city if lead else '',
                    'state': lead.state if lead else '',
                    'zip_code': lead.zip_code if lead else '',
                    'country': lead.country if lead else '',
                    'notes': lead.notes if lead else 'Test call',
                    'metadata': lead.metadata if lead else {'test_call': True, 'call_task_id': str(call_task.id)},
                }
                
                agent_phone = agent.phone_numbers.first().phonenumber if agent.phone_numbers.exists() else None
                from_number = agent_phone or getattr(workspace, 'phone_number', None) or os.getenv('DEFAULT_FROM_NUMBER')
                campaign_id = str(workspace.id)
                call_reason = None if lead else "Test call - triggered manually"
                
        except CallTask.DoesNotExist:
            logger.error(f"❌ CallTask {call_task_id} not found (deleted during processing)")
            return {
                'success': False,
                'error': 'CallTask not found',
                'call_task_id': call_task_id
            }
        
        logger.info(f"📞 Starting call for task {call_task_id} to {lead_data['phone']} (passed safety checks)")
        
        # 🚀 DIRECT ASYNC CALL (zero coupling) - This happens OUTSIDE transaction
        from core.utils.livekit_calls import _make_call_async
        call_result = asyncio.run(_make_call_async(
            sip_trunk_id=sip_trunk_id,
            agent_config=agent_config,
            lead_data=lead_data,
            from_number=from_number,
            campaign_id=campaign_id,
            call_reason=call_reason
        ))
        
        # 🔒 ATOMIC: Handle call result and update status atomically
        try:
            with transaction.atomic():
                # Re-fetch task with lock to get fresh data
                call_task = CallTask.objects.select_for_update().get(id=call_task_id)
                
                # Verify task is still IN_PROGRESS (could have been modified)
                if call_task.status != CallStatus.IN_PROGRESS:
                    logger.warning(f"⚠️ Task {call_task_id} status changed to {call_task.status} during call execution")
                    return {
                        'success': False,
                        'call_task_id': call_task_id,
                        'reason': 'status_changed_during_call',
                        'current_status': call_task.status,
                        'call_result': call_result
                    }
                
                if call_result.get('success', False):
                    # 🎉 CALL SUCCESSFUL: Mark as SCHEDULED for future scheduling
                    # NOTE: Could be COMPLETED if you want one-time calls only
                    call_task.status = CallStatus.SCHEDULED
                    call_task.save(update_fields=['status', 'updated_at'])
                    
                    logger.info(f"✅ Call successfully initiated for task {call_task_id}")
                    
                    return {
                        'success': True,
                        'call_task_id': call_task_id,
                        'call_result': call_result,
                        'message': 'Call initiated successfully'
                    }
                else:
                    # 💥 CALL FAILED: Implement atomic retry logic
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
                    
        except CallTask.DoesNotExist:
            logger.error(f"❌ CallTask {call_task_id} was deleted during call execution")
            return {
                'success': False,
                'error': 'CallTask was deleted during execution',
                'call_task_id': call_task_id,
                'call_result': call_result
            }
        except Exception as result_error:
            logger.error(f"❌ Failed to process call result for task {call_task_id}: {result_error}")
            # Try to reset task to RETRY state atomically
            try:
                with transaction.atomic():
                    call_task = CallTask.objects.select_for_update().get(id=call_task_id)
                    call_task.status = CallStatus.RETRY
                    call_task.save(update_fields=['status', 'updated_at'])
                    logger.info(f"🔄 Reset task {call_task_id} to RETRY after result processing error")
            except Exception as reset_error:
                logger.error(f"❌ Failed to reset task {call_task_id}: {reset_error}")
            
            return {
                'success': False,
                'error': f'Result processing failed: {result_error}',
                'call_task_id': call_task_id,
                'call_result': call_result
            }
            
    except Exception as e:
        logger.error(f"❌ Trigger call task failed for {call_task_id}: {str(e)}")
        
        # 🔄 ATOMIC: Try to update task status to RETRY if possible
        try:
            with transaction.atomic():
                call_task = CallTask.objects.select_for_update().get(id=call_task_id)
                call_task.status = CallStatus.RETRY
                call_task.save(update_fields=['status', 'updated_at'])
                logger.info(f"🔄 Reset task {call_task_id} to RETRY after exception")
        except CallTask.DoesNotExist:
            logger.error(f"❌ CallTask {call_task_id} not found for error recovery")
        except Exception as recovery_error:
            logger.error(f"❌ Failed to reset task {call_task_id} during error recovery: {recovery_error}")
        
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
    
    from django.db import transaction
    
    try:
        now = timezone.now()
        
        # Calculate concurrency limit from database
        from core.models import LiveKitAgent
        agents = LiveKitAgent.objects.filter(expires_at__gt=timezone.now())
        total_concurrency = sum(agent.concurrency_per_agent for agent in agents)
        concurrency_limit = max(total_concurrency, 1)  # At least 1 to prevent division by zero
        
        # 🔒 SINGLE ATOMIC TRANSACTION: ALL logic including concurrency check inside transaction
        scheduled_count = 0
        scheduled_task_ids = []
        tasks_to_trigger = []
        
        with transaction.atomic():
            # 🔒 ATOMIC: Get fresh concurrency data with row locks
            current_in_progress = CallTask.objects.select_for_update().filter(
                status=CallStatus.IN_PROGRESS
            ).count()
            
            # Calculate available slots with FRESH atomic data
            available_slots = concurrency_limit - current_in_progress
            
            logger.info(f"📊 Atomic scheduling check: {current_in_progress} in progress, {concurrency_limit} limit, {available_slots} slots available")
            
            if available_slots <= 0:
                return {
                    'success': True,
                    'scheduled_count': 0,
                    'in_progress_count': current_in_progress,
                    'concurrency_limit': concurrency_limit,
                    'message': 'No available slots after atomic check'
                }
            
            # 🔒 ATOMIC: Get ready tasks with row locks to prevent race conditions
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
            ).order_by('priority', 'next_call')[:available_slots]
            
            # 🔒 ATOMIC: Check for phone conflicts within same transaction
            if ready_tasks:
                phone_numbers = [task.phone for task in ready_tasks]
                conflicting_phones = set(CallTask.objects.select_for_update().filter(
                    phone__in=phone_numbers,
                    status__in=[CallStatus.IN_PROGRESS, CallStatus.CALL_TRIGGERED]
                ).values_list('phone', flat=True))
                
                # Filter out tasks with phone conflicts
                safe_tasks = [task for task in ready_tasks if task.phone not in conflicting_phones]
            else:
                safe_tasks = []
            
            # 🔒 ATOMIC: Update all safe tasks to CALL_TRIGGERED in single transaction
            for task in safe_tasks:
                # Task is already locked from select_for_update query above
                task.status = CallStatus.CALL_TRIGGERED
                task.save(update_fields=['status', 'updated_at'])
                
                tasks_to_trigger.append(str(task.id))
                scheduled_count += 1
                scheduled_task_ids.append(str(task.id))
                
                logger.info(f"📞 Atomically scheduled call task {task.id} for {task.phone}")
        
        # 🚀 AFTER atomic transaction commits successfully → Spawn async tasks
        for task_id in tasks_to_trigger:
            try:
                trigger_call.delay(task_id)
                logger.info(f"✅ Triggered async call for task {task_id}")
            except Exception as e:
                logger.error(f"❌ Failed to trigger async call for task {task_id}: {e}")
                # Reset task status in separate transaction if async spawn fails
                try:
                    with transaction.atomic():
                        failed_task = CallTask.objects.select_for_update().get(id=task_id)
                        if failed_task.status == CallStatus.CALL_TRIGGERED:
                            failed_task.status = CallStatus.SCHEDULED
                            failed_task.save(update_fields=['status', 'updated_at'])
                            logger.info(f"🔄 Reset task {task_id} from CALL_TRIGGERED to SCHEDULED")
                except Exception as reset_error:
                    logger.error(f"❌ Failed to reset task {task_id}: {reset_error}")
        
        logger.info(f"✅ Scheduled {scheduled_count} call tasks out of {available_slots} available slots")
        
        return {
            'success': True,
            'scheduled_count': scheduled_count,
            'scheduled_task_ids': scheduled_task_ids,
            'in_progress_count': current_in_progress,
            'concurrency_limit': concurrency_limit,
            'available_slots': available_slots,
            'timestamp': now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Schedule agent call task failed: {str(e)}")
        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
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
    
    from django.db import transaction
    
    try:
        now = timezone.now()
        
        # Calculate cleanup thresholds
        call_triggered_threshold = now - timedelta(minutes=10)
        in_progress_threshold = now - timedelta(minutes=30)
        
        # 🔒 SINGLE ATOMIC TRANSACTION: All cleanup logic in one transaction
        with transaction.atomic():
            # Find CALL_TRIGGERED tasks older than 10 minutes
            # 🔒 ATOMIC: Lock rows to prevent race conditions during cleanup
            stuck_triggered_tasks = CallTask.objects.select_for_update().filter(
                status=CallStatus.CALL_TRIGGERED,
                updated_at__lt=call_triggered_threshold
            )
            triggered_count = stuck_triggered_tasks.count()
            
            # Find IN_PROGRESS tasks older than 30 minutes  
            # 🔒 ATOMIC: Lock rows to prevent race conditions during cleanup
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
            triggered_ids = []
            progress_ids = []
            
            if triggered_count > 0:
                triggered_ids = list(stuck_triggered_tasks.values_list('id', flat=True))
                logger.warning(f"🗑️ Deleting CALL_TRIGGERED tasks (>10min): {triggered_ids}")
                
            if progress_count > 0:
                progress_ids = list(stuck_progress_tasks.values_list('id', flat=True))  
                logger.warning(f"🗑️ Deleting IN_PROGRESS tasks (>30min): {progress_ids}")
            
            # 🔒 ATOMIC: HARD DELETE stuck tasks within transaction
            # This ensures either ALL deletions succeed or NONE (rollback)
            triggered_deleted = 0
            progress_deleted = 0
            
            if triggered_count > 0:
                triggered_deleted = stuck_triggered_tasks.delete()[0]
                
            if progress_count > 0:
                progress_deleted = stuck_progress_tasks.delete()[0]
                
            total_deleted = triggered_deleted + progress_deleted
        
        logger.info(f"✅ Cleanup complete: Deleted {total_deleted} stuck call tasks ({triggered_deleted} CALL_TRIGGERED + {progress_deleted} IN_PROGRESS)")
        
        return {
            'success': True,
            'deleted_triggered': triggered_deleted,
            'deleted_progress': progress_deleted,
            'total_deleted': total_deleted,
            'message': f'Successfully deleted {total_deleted} stuck tasks',
            'timestamp': now.isoformat(),
            'call_triggered_threshold': call_triggered_threshold.isoformat(),
            'in_progress_threshold': in_progress_threshold.isoformat(),
            'triggered_task_ids': triggered_ids,
            'progress_task_ids': progress_ids
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
