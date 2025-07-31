"""
Celery tasks for HotCalls application.
"""
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
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
