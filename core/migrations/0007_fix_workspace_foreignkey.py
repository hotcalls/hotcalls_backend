# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_update_calltask_final'),
    ]

    operations = [
        # Change workspace from OneToOneField to ForeignKey
        migrations.AlterField(
            model_name='calltask',
            name='workspace',
            field=models.ForeignKey(help_text='Workspace associated with this call task', on_delete=django.db.models.deletion.CASCADE, related_name='call_tasks', to='core.workspace'),
        ),
    ] 