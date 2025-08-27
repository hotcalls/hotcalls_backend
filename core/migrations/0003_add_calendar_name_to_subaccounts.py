# Generated migration to add calendar_name field to sub-accounts

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='googlesubaccount',
            name='calendar_name',
            field=models.CharField(
                max_length=255,
                blank=True,
                default='',
                help_text='Human-readable calendar name'
            ),
        ),
        migrations.AddField(
            model_name='outlooksubaccount',
            name='calendar_name',
            field=models.CharField(
                max_length=255,
                blank=True,
                default='',
                help_text='Human-readable calendar name'
            ),
        ),
    ]
