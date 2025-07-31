# Generated manually for LiveKit Agent Table

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_auto_20250731_1417'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiveKitAgent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(help_text='Unique agent name for LiveKit authentication', max_length=255, unique=True)),
                ('token', models.CharField(help_text='Random string token for authentication', max_length=64, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(help_text='Token expiration date (1 year from creation)')),
            ],
            options={
                'db_table': 'core_livekit_agent',
            },
        ),
        migrations.AddIndex(
            model_name='livekitagent',
            index=models.Index(fields=['token'], name='core_liveki_token_b4a5d5_idx'),
        ),
        migrations.AddIndex(
            model_name='livekitagent',
            index=models.Index(fields=['name'], name='core_liveki_name_3f1e82_idx'),
        ),
        migrations.AddIndex(
            model_name='livekitagent',
            index=models.Index(fields=['expires_at'], name='core_liveki_expires_9b2c41_idx'),
        ),
    ] 