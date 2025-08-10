# Generated manually to remove deprecated OAuth fields from GoogleCalendar

from django.db import migrations


class Migration(migrations.Migration):
    
    dependencies = [
        ('core', '0005_add_is_active_to_meta_lead_form'),
    ]
    
    operations = [
        migrations.RemoveField(
            model_name='googlecalendar',
            name='refresh_token',
        ),
        migrations.RemoveField(
            model_name='googlecalendar',
            name='access_token',
        ),
        migrations.RemoveField(
            model_name='googlecalendar',
            name='token_expires_at',
        ),
        migrations.RemoveField(
            model_name='googlecalendar',
            name='scopes',
        ),
    ] 