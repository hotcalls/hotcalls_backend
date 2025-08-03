# Generated migration for adding access_role field to GoogleCalendar

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_populate_google_calendar_connections'),
    ]

    operations = [
        migrations.AddField(
            model_name='googlecalendar',
            name='access_role',
            field=models.CharField(
                choices=[
                    ('freeBusyReader', 'Free/Busy Reader'),
                    ('reader', 'Reader'),
                    ('writer', 'Writer'),
                    ('owner', 'Owner'),
                ],
                default='reader',
                help_text='Access level for this calendar',
                max_length=20
            ),
        ),
    ] 