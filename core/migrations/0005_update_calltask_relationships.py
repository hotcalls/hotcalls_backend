# Generated manually

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_workspace_has_used_trial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Remove old fields
        migrations.RemoveField(
            model_name='calltask',
            name='retries',
        ),
        migrations.RemoveField(
            model_name='calltask',
            name='read',
        ),
        migrations.RemoveField(
            model_name='calltask',
            name='usp',
        ),
        migrations.RemoveField(
            model_name='calltask',
            name='bscript',
        ),
        
        # Add new fields
        migrations.AddField(
            model_name='calltask',
            name='attempts',
            field=models.IntegerField(default=0, help_text='Number of retry attempts made'),
        ),
        migrations.AddField(
            model_name='calltask',
            name='is_test',
            field=models.BooleanField(default=False, help_text='Whether this is a test call'),
        ),
        
        # Add OneToOne fields
        migrations.AddField(
            model_name='calltask',
            name='workspace',
            field=models.OneToOneField(default=1, help_text='Workspace associated with this call task', on_delete=django.db.models.deletion.CASCADE, related_name='call_task', to='core.workspace'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='calltask',
            name='user',
            field=models.OneToOneField(default=1, help_text='User associated with this call task', on_delete=django.db.models.deletion.CASCADE, related_name='call_task', to=settings.AUTH_USER_MODEL),
            preserve_default=False,
        ),
        
        # Change lead from ForeignKey to OneToOneField
        migrations.AlterField(
            model_name='calltask',
            name='lead',
            field=models.OneToOneField(help_text='Lead associated with this call task', on_delete=django.db.models.deletion.CASCADE, related_name='call_task', to='core.lead'),
        ),
        
        # Update status field to use new choices
        migrations.AlterField(
            model_name='calltask',
            name='status',
            field=models.CharField(choices=[('PEND', 'pending'), ('STRT', 'starting'), ('ACTV', 'active'), ('SUCC', 'success'), ('FAIL', 'failed')], default='PEND', help_text='Current status of the call task', max_length=20),
        ),
        
        # Make next_call required (remove null=True, blank=True)
        migrations.AlterField(
            model_name='calltask',
            name='next_call',
            field=models.DateTimeField(help_text='Scheduled time for the next call attempt'),
        ),
    ] 