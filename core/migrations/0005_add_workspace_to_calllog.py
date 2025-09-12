# Generated manually for workspace field addition with data migration
from django.db import migrations, models
import django.db.models.deletion


def populate_workspace_from_agent(apps, schema_editor):
    """
    Populate the new workspace field using the agent.workspace relationship
    """
    CallLog = apps.get_model('core', 'CallLog')
    
    # Update all CallLog records to set workspace from agent.workspace
    for calllog in CallLog.objects.select_related('agent__workspace').all():
        calllog.workspace_id = calllog.agent.workspace_id
        calllog.save(update_fields=['workspace'])


def reverse_workspace_population(apps, schema_editor):
    """
    Reverse operation - no-op since we're removing the field
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_add_transcript_to_calllog'),
    ]

    operations = [
        # Step 1: Add the workspace field as nullable
        migrations.AddField(
            model_name='calllog',
            name='workspace',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='call_logs',
                to='core.workspace',
                help_text='Workspace this call log belongs to'
            ),
        ),
        
        # Step 2: Populate workspace field from agent.workspace
        migrations.RunPython(
            populate_workspace_from_agent,
            reverse_workspace_population,
        ),
        
        # Step 3: Make the field non-nullable
        migrations.AlterField(
            model_name='calllog',
            name='workspace',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='call_logs',
                to='core.workspace',
                help_text='Workspace this call log belongs to'
            ),
        ),
        
        # Step 4: Add database index for better query performance
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS calllog_workspace_idx ON core_calllog(workspace_id);",
            reverse_sql="DROP INDEX IF EXISTS calllog_workspace_idx;"
        ),
    ]