# Migration to fix CASCADE delete for calendar relationships

from django.db import migrations

def fix_cascade_constraints(apps, schema_editor):
    """Fix foreign key constraints to use CASCADE delete"""
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            # Fix GoogleCalendar -> Calendar cascade
            cursor.execute("""
                ALTER TABLE core_googlecalendar 
                DROP CONSTRAINT IF EXISTS core_googlecalendar_calendar_id_fkey;
                
                ALTER TABLE core_googlecalendar 
                ADD CONSTRAINT core_googlecalendar_calendar_id_fkey 
                FOREIGN KEY (calendar_id) REFERENCES core_calendar(id) 
                ON DELETE CASCADE;
            """)
            
            # Fix OutlookCalendar -> Calendar cascade
            cursor.execute("""
                ALTER TABLE core_outlookcalendar 
                DROP CONSTRAINT IF EXISTS core_outlookcalendar_calendar_id_fkey;
                
                ALTER TABLE core_outlookcalendar 
                ADD CONSTRAINT core_outlookcalendar_calendar_id_fkey 
                FOREIGN KEY (calendar_id) REFERENCES core_calendar(id) 
                ON DELETE CASCADE;
            """)
            
            # Fix GoogleSubAccount -> GoogleCalendar cascade (should already be CASCADE but let's ensure)
            cursor.execute("""
                ALTER TABLE core_googlesubaccount 
                DROP CONSTRAINT IF EXISTS core_googlesubaccount_google_calendar_id_fkey;
                
                ALTER TABLE core_googlesubaccount 
                ADD CONSTRAINT core_googlesubaccount_google_calendar_id_fkey 
                FOREIGN KEY (google_calendar_id) REFERENCES core_googlecalendar(id) 
                ON DELETE CASCADE;
            """)
            
            # Fix OutlookSubAccount -> OutlookCalendar cascade
            cursor.execute("""
                ALTER TABLE core_outlooksubaccount 
                DROP CONSTRAINT IF EXISTS core_outlooksubaccount_outlook_calendar_id_fkey;
                
                ALTER TABLE core_outlooksubaccount 
                ADD CONSTRAINT core_outlooksubaccount_outlook_calendar_id_fkey 
                FOREIGN KEY (outlook_calendar_id) REFERENCES core_outlookcalendar(id) 
                ON DELETE CASCADE;
            """)

def reverse_cascade_constraints(apps, schema_editor):
    """Reverse the CASCADE constraints back to NO ACTION"""
    # We don't really want to reverse this, but Django requires it
    pass

class Migration(migrations.Migration):
    
    dependencies = [
        ('core', '0001_initial'),
    ]
    
    operations = [
        migrations.RunPython(fix_cascade_constraints, reverse_cascade_constraints),
    ]
