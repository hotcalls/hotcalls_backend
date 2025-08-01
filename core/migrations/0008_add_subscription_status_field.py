from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_remove_trial_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspace',
            name='subscription_status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('none', 'None'),
                    ('trial', 'Trial'),
                    ('active', 'Active'),
                    ('past_due', 'Past Due'),
                    ('unpaid', 'Unpaid'),
                    ('cancelled', 'Cancelled'),
                ],
                default='none',
                help_text='Current subscription status (mirrors Stripe status)',
            ),
        ),
    ] 