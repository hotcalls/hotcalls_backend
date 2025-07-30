# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_update_calltask_relationships'),
    ]

    operations = [
        # Remove is_test field
        migrations.RemoveField(
            model_name='calltask',
            name='is_test',
        ),
        
        # Remove user OneToOneField
        migrations.RemoveField(
            model_name='calltask',
            name='user',
        ),
        
        # Add phone field
        migrations.AddField(
            model_name='calltask',
            name='phone',
            field=models.CharField(default='+1234567890', help_text='Phone number to call', max_length=20),
            preserve_default=False,
        ),
        
        # Make lead nullable
        migrations.AlterField(
            model_name='calltask',
            name='lead',
            field=models.OneToOneField(blank=True, help_text='Lead associated with this call task (null for test calls)', null=True, on_delete=models.deletion.CASCADE, related_name='call_task', to='core.lead'),
        ),
        
        # Update status field with new choices and default
        migrations.AlterField(
            model_name='calltask',
            name='status',
            field=models.CharField(choices=[('scheduled', 'scheduled'), ('in_progress', 'in_progress'), ('retry', 'retry'), ('waiting', 'waiting')], default='scheduled', help_text='Current status of the call task', max_length=20),
        ),
    ] 