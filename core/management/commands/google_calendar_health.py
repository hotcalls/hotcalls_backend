"""
Enhanced Google Calendar Health Management Command

This command provides comprehensive health monitoring for Google Calendar connections
including token status, connection health, and proactive issue detection.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

from core.models import GoogleCalendar, GoogleCalendarConnection, Calendar
from core.services.google_calendar import GoogleCalendarService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Comprehensive Google Calendar health monitoring and management'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check-all',
            action='store_true',
            help='Check health of all Google Calendar connections'
        )
        parser.add_argument(
            '--refresh-tokens',
            action='store_true',
            help='Attempt to refresh tokens for calendars needing it'
        )
        parser.add_argument(
            '--force-refresh',
            action='store_true',
            help='Force refresh all tokens regardless of expiry'
        )
        parser.add_argument(
            '--cleanup-expired',
            action='store_true',
            help='Clean up tokens expired for more than 7 days'
        )
        parser.add_argument(
            '--workspace-id',
            type=int,
            help='Check health for specific workspace only'
        )
        parser.add_argument(
            '--export-issues',
            action='store_true',
            help='Export health issues to JSON for monitoring systems'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output for each calendar'
        )

    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity', 1)
        self.verbose = options.get('verbose', False)
        
        # Header
        self.stdout.write(
            self.style.SUCCESS('\n🏥 GOOGLE CALENDAR HEALTH MONITORING SYSTEM\n')
        )
        
        # Get calendars to check based on workspace filter
        if options.get('workspace_id'):
            connections = GoogleCalendarConnection.objects.filter(
                workspace_id=options['workspace_id']
            )
            self.stdout.write(f"🎯 Filtering by workspace ID: {options['workspace_id']}")
        else:
            connections = GoogleCalendarConnection.objects.all()
        
        # Execute requested operations
        if options.get('check_all') or not any([
            options.get('refresh_tokens'),
            options.get('cleanup_expired'),
            options.get('force_refresh')
        ]):
            health_report = self.comprehensive_health_check(connections)
            
            if options.get('export_issues'):
                self.export_health_issues(health_report)
                
        if options.get('refresh_tokens') or options.get('force_refresh'):
            self.refresh_tokens(connections, force=options.get('force_refresh'))
            
        if options.get('cleanup_expired'):
            self.cleanup_expired_tokens()

    def comprehensive_health_check(self, connections):
        """Perform comprehensive health check on all calendar connections"""
        self.stdout.write(
            self.style.WARNING('\n🔍 COMPREHENSIVE HEALTH CHECK\n')
        )
        
        health_report = {
            'total_connections': 0,
            'healthy_connections': 0,
            'token_issues': [],
            'expired_tokens': [],
            'missing_tokens': [],
            'connection_errors': [],
            'workspace_summary': {},
            'critical_issues': [],
            'warnings': []
        }
        
        now = timezone.now()
        warning_threshold = now + timedelta(hours=24)  # Warn if expires in 24h
        
        for connection in connections:
            health_report['total_connections'] += 1
            workspace_name = connection.workspace.workspace_name
            
            # Initialize workspace summary
            if workspace_name not in health_report['workspace_summary']:
                health_report['workspace_summary'][workspace_name] = {
                    'total': 0,
                    'healthy': 0,
                    'issues': 0
                }
            
            health_report['workspace_summary'][workspace_name]['total'] += 1
            
            try:
                # Check token status
                token_status = self._check_token_health(connection, now, warning_threshold)
                
                if token_status['status'] == 'healthy':
                    # Test actual connection
                    connection_status = self._test_connection_health(connection)
                    
                    if connection_status['success']:
                        health_report['healthy_connections'] += 1
                        health_report['workspace_summary'][workspace_name]['healthy'] += 1
                        
                        if self.verbose:
                            self.stdout.write(
                                self.style.SUCCESS(f"✅ {connection.account_email} ({workspace_name}): Healthy")
                            )
                    else:
                        health_report['connection_errors'].append({
                            'email': connection.account_email,
                            'workspace': workspace_name,
                            'error': connection_status['error']
                        })
                        health_report['workspace_summary'][workspace_name]['issues'] += 1
                        
                        if self.verbose:
                            self.stdout.write(
                                self.style.ERROR(f"❌ {connection.account_email} ({workspace_name}): Connection failed - {connection_status['error']}")
                            )
                else:
                    # Handle token issues
                    if token_status['status'] == 'missing':
                        health_report['missing_tokens'].append({
                            'email': connection.account_email,
                            'workspace': workspace_name,
                            'reason': token_status['reason']
                        })
                        health_report['critical_issues'].append(f"MISSING TOKENS: {connection.account_email}")
                    elif token_status['status'] == 'expired':
                        health_report['expired_tokens'].append({
                            'email': connection.account_email,
                            'workspace': workspace_name,
                            'expired_since': token_status.get('expired_since'),
                            'reason': token_status['reason']
                        })
                        health_report['critical_issues'].append(f"EXPIRED TOKENS: {connection.account_email}")
                    elif token_status['status'] == 'expiring_soon':
                        health_report['warnings'].append(f"TOKENS EXPIRE SOON: {connection.account_email}")
                    
                    health_report['workspace_summary'][workspace_name]['issues'] += 1
                    
                    if self.verbose:
                        self.stdout.write(
                            self.style.WARNING(f"⚠️ {connection.account_email} ({workspace_name}): {token_status['reason']}")
                        )
                        
            except Exception as e:
                health_report['connection_errors'].append({
                    'email': connection.account_email,
                    'workspace': workspace_name,
                    'error': f"Unexpected error: {str(e)}"
                })
                health_report['workspace_summary'][workspace_name]['issues'] += 1
                
                if self.verbose:
                    self.stdout.write(
                        self.style.ERROR(f"💥 {connection.account_email} ({workspace_name}): Unexpected error - {str(e)}")
                    )
        
        # Print summary
        self._print_health_summary(health_report)
        
        return health_report

    def _check_token_health(self, connection, now, warning_threshold):
        """Check the health status of tokens for a connection"""
        if not connection.access_token or not connection.refresh_token:
            return {
                'status': 'missing',
                'reason': 'Missing access or refresh token'
            }
        
        if not connection.token_expires_at:
            return {
                'status': 'unknown_expiry',
                'reason': 'Token expiry time unknown'
            }
        
        # Make timezone aware for comparison
        if connection.token_expires_at.tzinfo is None:
            token_expiry = connection.token_expires_at.replace(tzinfo=timezone.utc)
        else:
            token_expiry = connection.token_expires_at
        
        if token_expiry <= now:
            expired_since = now - token_expiry
            return {
                'status': 'expired',
                'reason': f'Token expired {expired_since.days} days ago',
                'expired_since': expired_since.days
            }
        elif token_expiry <= warning_threshold:
            hours_until_expiry = (token_expiry - now).total_seconds() / 3600
            return {
                'status': 'expiring_soon',
                'reason': f'Token expires in {hours_until_expiry:.1f} hours'
            }
        else:
            return {
                'status': 'healthy',
                'reason': 'Token is valid and not expiring soon'
            }

    def _test_connection_health(self, connection):
        """Test actual Google API connection"""
        try:
            service = GoogleCalendarService(connection)
            result = service.test_connection()
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _print_health_summary(self, health_report):
        """Print comprehensive health summary"""
        self.stdout.write('\n📊 HEALTH SUMMARY')
        self.stdout.write('=' * 50)
        
        total = health_report['total_connections']
        healthy = health_report['healthy_connections']
        issues = total - healthy
        
        # Overall status
        if issues == 0:
            self.stdout.write(
                self.style.SUCCESS(f"🟢 SYSTEM HEALTHY: {healthy}/{total} connections working perfectly")
            )
        elif issues < total * 0.1:  # Less than 10% issues
            self.stdout.write(
                self.style.WARNING(f"🟡 MINOR ISSUES: {healthy}/{total} connections healthy, {issues} need attention")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"🔴 CRITICAL ISSUES: {healthy}/{total} connections healthy, {issues} failing")
            )
        
        # Detailed breakdown
        if health_report['missing_tokens']:
            self.stdout.write(
                self.style.ERROR(f"\n🚨 MISSING TOKENS ({len(health_report['missing_tokens'])} accounts):")
            )
            for item in health_report['missing_tokens']:
                self.stdout.write(f"   • {item['email']} ({item['workspace']})")
        
        if health_report['expired_tokens']:
            self.stdout.write(
                self.style.ERROR(f"\n⏰ EXPIRED TOKENS ({len(health_report['expired_tokens'])} accounts):")
            )
            for item in health_report['expired_tokens']:
                self.stdout.write(f"   • {item['email']} ({item['workspace']}) - {item['reason']}")
        
        if health_report['connection_errors']:
            self.stdout.write(
                self.style.ERROR(f"\n🔌 CONNECTION ERRORS ({len(health_report['connection_errors'])} accounts):")
            )
            for item in health_report['connection_errors']:
                self.stdout.write(f"   • {item['email']} ({item['workspace']}) - {item['error']}")
        
        # Workspace breakdown
        self.stdout.write('\n🏢 WORKSPACE BREAKDOWN:')
        for workspace, stats in health_report['workspace_summary'].items():
            if stats['issues'] == 0:
                status_icon = "🟢"
                status_style = self.style.SUCCESS
            elif stats['issues'] < stats['total'] * 0.3:
                status_icon = "🟡"
                status_style = self.style.WARNING
            else:
                status_icon = "🔴"
                status_style = self.style.ERROR
            
            self.stdout.write(
                status_style(f"   {status_icon} {workspace}: {stats['healthy']}/{stats['total']} healthy")
            )
        
        # Action recommendations
        self.stdout.write('\n💡 RECOMMENDED ACTIONS:')
        if health_report['missing_tokens'] or health_report['expired_tokens']:
            self.stdout.write("   • Run --refresh-tokens to attempt automatic token refresh")
            self.stdout.write("   • For failed refreshes, users need to re-authorize their Google Calendar")
        if health_report['connection_errors']:
            self.stdout.write("   • Check network connectivity and Google API status")
        if not any([health_report['missing_tokens'], health_report['expired_tokens'], health_report['connection_errors']]):
            self.stdout.write("   • No issues detected! System is healthy.")

    def export_health_issues(self, health_report):
        """Export health issues for external monitoring systems"""
        import json
        from datetime import datetime
        
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_connections': health_report['total_connections'],
                'healthy_connections': health_report['healthy_connections'],
                'critical_issues_count': len(health_report['critical_issues']),
                'warnings_count': len(health_report['warnings'])
            },
            'critical_issues': health_report['critical_issues'],
            'warnings': health_report['warnings'],
            'workspace_health': health_report['workspace_summary']
        }
        
        filename = f"calendar_health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        self.stdout.write(
            self.style.SUCCESS(f"\n📄 Health report exported to: {filename}")
        ) 