# Generated manually on 2025-08-02 for GoogleCalendar connection population

from django.db import migrations


def populate_google_calendar_connections(apps, schema_editor):
    """
    Populate GoogleCalendar.connection field by matching with GoogleCalendarConnection
    based on workspace and external_id pattern matching.
    """
    GoogleCalendar = apps.get_model('core', 'GoogleCalendar')
    GoogleCalendarConnection = apps.get_model('core', 'GoogleCalendarConnection')
    Calendar = apps.get_model('core', 'Calendar')
    
    print("🔧 Populating GoogleCalendar connection fields...")
    
    # Get all GoogleCalendar entries that need connection
    google_calendars = GoogleCalendar.objects.select_related('calendar').all()
    
    updated_count = 0
    error_count = 0
    
    for gc in google_calendars:
        try:
            # Try to find matching connection by workspace and email pattern
            workspace = gc.calendar.workspace
            
            # Try to match by external_id (often contains email)
            external_id = gc.external_id
            
            # Look for connection that could provide access to this calendar
            potential_connections = GoogleCalendarConnection.objects.filter(
                workspace=workspace,
                active=True
            )
            
            connection = None
            
            # Strategy 1: Direct email match in external_id
            for conn in potential_connections:
                if conn.account_email in external_id or external_id == conn.account_email:
                    connection = conn
                    break
            
            # Strategy 2: Take first active connection for this workspace
            if not connection and potential_connections.exists():
                connection = potential_connections.first()
                print(f"  📋 Using first available connection for {gc.external_id}")
            
            if connection:
                gc.connection = connection
                gc.save(update_fields=['connection'])
                updated_count += 1
                print(f"  ✅ Connected {gc.external_id} to {connection.account_email}")
            else:
                print(f"  ⚠️ No connection found for {gc.external_id} in workspace {workspace.workspace_name}")
                error_count += 1
                
        except Exception as e:
            print(f"  ❌ Error processing {gc.external_id}: {str(e)}")
            error_count += 1
    
    print(f"📊 Migration completed: {updated_count} connected, {error_count} errors")


def reverse_populate_google_calendar_connections(apps, schema_editor):
    """
    Reverse migration - clear all connection fields
    """
    GoogleCalendar = apps.get_model('core', 'GoogleCalendar')
    
    print("🔄 Clearing GoogleCalendar connection fields...")
    
    updated_count = GoogleCalendar.objects.update(connection=None)
    
    print(f"📊 Cleared {updated_count} connection fields")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_add_nullable_connection_field'),
    ]

    operations = [
        migrations.RunPython(
            populate_google_calendar_connections,
            reverse_populate_google_calendar_connections,
        ),
    ] 