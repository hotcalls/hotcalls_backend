"""
Celery tasks for HotCalls application.
"""
import logging
from datetime import datetime, timedelta
from celery import shared_task
from django.utils import timezone
from django.conf import settings

from core.models import GoogleCalendarConnection
from core.services.google_calendar import GoogleCalendarService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def refresh_google_calendar_connections(self):
    """
    Periodic task to refresh Google Calendar connections and sync calendars.
    
    This task:
    1. Finds connections with tokens expiring soon
    2. Refreshes access tokens using refresh tokens
    3. Syncs calendar lists from Google
    4. Handles errors and marks failed connections
    
    Recommended to run every 15 minutes.
    """
    try:
        # Find connections that need token refresh (expire in next 5 minutes)
        expiry_threshold = timezone.now() + timedelta(minutes=5)
        
        connections_to_refresh = GoogleCalendarConnection.objects.filter(
            active=True,
            token_expires_at__lte=expiry_threshold
        )
        
        total_connections = connections_to_refresh.count()
        refreshed_count = 0
        error_count = 0
        
        logger.info(f"Found {total_connections} Google Calendar connections needing token refresh")
        
        for connection in connections_to_refresh:
            try:
                service = GoogleCalendarService(connection)
                
                # This will automatically refresh the token if needed
                test_result = service.test_connection()
                
                if test_result['success']:
                    # Sync calendars if token was refreshed successfully
                    sync_google_calendars.delay(connection.id)
                    refreshed_count += 1
                    logger.info(f"Refreshed tokens for {connection.account_email}")
                else:
                    logger.warning(f"Connection test failed for {connection.account_email}: {test_result.get('error')}")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to refresh connection {connection.account_email}: {str(e)}")
                
                # Store error information
                connection.sync_errors = {
                    'last_error': str(e),
                    'timestamp': timezone.now().isoformat(),
                    'error_type': 'token_refresh_failed'
                }
                connection.save(update_fields=['sync_errors', 'updated_at'])
                error_count += 1
        
        logger.info(f"Token refresh completed: {refreshed_count} successful, {error_count} errors")
        
        return {
            'total_connections': total_connections,
            'refreshed': refreshed_count,
            'errors': error_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Token refresh task failed: {str(e)}")
        # Retry the task
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def sync_google_calendars(self, connection_id):
    """
    Sync calendar list for a specific Google Calendar connection.
    
    Args:
        connection_id: UUID of the GoogleCalendarConnection
    """
    try:
        connection = GoogleCalendarConnection.objects.get(
            id=connection_id,
            active=True
        )
        
        service = GoogleCalendarService(connection)
        synced_calendars = service.sync_calendars()
        
        logger.info(f"Synced {len(synced_calendars)} calendars for {connection.account_email}")
        
        return {
            'connection_id': connection_id,
            'account_email': connection.account_email,
            'calendars_synced': len(synced_calendars),
            'timestamp': timezone.now().isoformat()
        }
        
    except GoogleCalendarConnection.DoesNotExist:
        logger.warning(f"GoogleCalendarConnection {connection_id} not found or inactive")
        return {
            'connection_id': connection_id,
            'error': 'Connection not found or inactive',
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to sync calendars for connection {connection_id}: {str(e)}")
        
        # Store error in connection
        try:
            connection = GoogleCalendarConnection.objects.get(id=connection_id)
            connection.sync_errors = {
                'last_error': str(e),
                'timestamp': timezone.now().isoformat(),
                'error_type': 'calendar_sync_failed'
            }
            connection.save(update_fields=['sync_errors', 'updated_at'])
        except:
            pass
        
        # Retry the task
        raise self.retry(exc=e, countdown=120)


@shared_task(bind=True, max_retries=3)
def full_calendar_sync(self):
    """
    Full synchronization of all active Google Calendar connections.
    
    This task:
    1. Refreshes all tokens that need refreshing
    2. Syncs calendar lists for all active connections
    3. Cleans up inactive connections
    
    Recommended to run daily.
    """
    try:
        active_connections = GoogleCalendarConnection.objects.filter(active=True)
        total_connections = active_connections.count()
        success_count = 0
        error_count = 0
        
        logger.info(f"Starting full calendar sync for {total_connections} connections")
        
        for connection in active_connections:
            try:
                service = GoogleCalendarService(connection)
                
                # Test connection and refresh token if needed
                test_result = service.test_connection()
                
                if test_result['success']:
                    # Sync calendars
                    synced_calendars = service.sync_calendars()
                    success_count += 1
                    logger.info(f"Successfully synced {len(synced_calendars)} calendars for {connection.account_email}")
                else:
                    logger.warning(f"Connection test failed for {connection.account_email}")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to sync connection {connection.account_email}: {str(e)}")
                error_count += 1
                
                # Store error
                connection.sync_errors = {
                    'last_error': str(e),
                    'timestamp': timezone.now().isoformat(),
                    'error_type': 'full_sync_failed'
                }
                connection.save(update_fields=['sync_errors', 'updated_at'])
        
        # Clean up old error records (connections that haven't been used in 30 days)
        cleanup_threshold = timezone.now() - timedelta(days=30)
        inactive_connections = GoogleCalendarConnection.objects.filter(
            active=True,
            last_sync__lt=cleanup_threshold
        )
        
        cleanup_count = 0
        for connection in inactive_connections:
            logger.warning(f"Marking inactive connection {connection.account_email} (last sync: {connection.last_sync})")
            connection.active = False
            connection.save()
            cleanup_count += 1
        
        logger.info(f"Full sync completed: {success_count} successful, {error_count} errors, {cleanup_count} cleaned up")
        
        return {
            'total_connections': total_connections,
            'successful': success_count,
            'errors': error_count,
            'cleaned_up': cleanup_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Full calendar sync task failed: {str(e)}")
        # Retry the task
        raise self.retry(exc=e, countdown=300)


@shared_task(bind=True, max_retries=3)
def cleanup_expired_connections(self):
    """
    Clean up expired Google Calendar connections.
    
    Marks connections as inactive if:
    1. Tokens are expired and refresh fails
    2. Connection hasn't been used in 60 days
    3. Account has been revoked at Google
    
    Recommended to run weekly.
    """
    try:
        cleanup_count = 0
        error_count = 0
        
        # Find connections that haven't been synced in 60 days
        old_threshold = timezone.now() - timedelta(days=60)
        old_connections = GoogleCalendarConnection.objects.filter(
            active=True,
            last_sync__lt=old_threshold
        )
        
        for connection in old_connections:
            try:
                # Try to test the connection
                service = GoogleCalendarService(connection)
                test_result = service.test_connection()
                
                if not test_result['success']:
                    logger.info(f"Deactivating old connection {connection.account_email}")
                    connection.active = False
                    connection.sync_errors = {
                        'last_error': 'Connection expired due to inactivity',
                        'timestamp': timezone.now().isoformat(),
                        'error_type': 'expired_connection'
                    }
                    connection.save()
                    cleanup_count += 1
                else:
                    # Connection is still valid, update last_sync
                    connection.last_sync = timezone.now()
                    connection.save()
                    
            except Exception as e:
                logger.error(f"Error testing old connection {connection.account_email}: {str(e)}")
                error_count += 1
        
        # Find connections with repeated sync errors
        error_threshold = timezone.now() - timedelta(days=7)
        error_connections = GoogleCalendarConnection.objects.filter(
            active=True,
            sync_errors__isnull=False,
            updated_at__lt=error_threshold
        )
        
        for connection in error_connections:
            logger.info(f"Deactivating connection with persistent errors: {connection.account_email}")
            connection.active = False
            connection.save()
            cleanup_count += 1
        
        logger.info(f"Cleanup completed: {cleanup_count} connections deactivated, {error_count} errors")
        
        return {
            'deactivated': cleanup_count,
            'errors': error_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Connection cleanup task failed: {str(e)}")
        raise self.retry(exc=e, countdown=600)


# Manual task helpers

@shared_task
def refresh_single_connection(connection_id):
    """Manually refresh a single Google Calendar connection"""
    return sync_google_calendars(connection_id)


@shared_task
def test_all_connections():
    """Test all Google Calendar connections and return status"""
    connections = GoogleCalendarConnection.objects.filter(active=True)
    results = []
    
    for connection in connections:
        try:
            service = GoogleCalendarService(connection)
            test_result = service.test_connection()
            results.append({
                'connection_id': connection.id,
                'account_email': connection.account_email,
                'status': 'success' if test_result['success'] else 'error',
                'details': test_result
            })
        except Exception as e:
            results.append({
                'connection_id': connection.id,
                'account_email': connection.account_email,
                'status': 'error',
                'error': str(e)
            })
    
    return {
        'total_tested': len(results),
        'results': results,
        'timestamp': timezone.now().isoformat()
    }
