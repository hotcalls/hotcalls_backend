from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_microsoftcalendarconnection_microsoftcalendar_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspace',
            name='creator',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_workspaces',
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name='workspace',
            name='admin_user',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='admin_workspaces',
                null=True,
                blank=True,
            ),
        ),
    ]


