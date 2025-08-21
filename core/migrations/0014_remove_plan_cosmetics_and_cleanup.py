from django.db import migrations


def cleanup_features(apps, schema_editor):
    Feature = apps.get_model('core', 'Feature')
    PlanFeature = apps.get_model('core', 'PlanFeature')
    # Remove unwanted features if they exist
    for fname in ['max_funnels', 'overage_rate_cents', 'whitelabel_solution', 'crm_integrations', 'priority_support', 'custom_voice_cloning', 'advanced_analytics']:
        try:
            feat = Feature.objects.get(feature_name=fname)
            PlanFeature.objects.filter(feature=feat).delete()
            feat.delete()
        except Feature.DoesNotExist:
            pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0013_create_endpointfeature_if_missing'),
    ]

    operations = [
        migrations.RunPython(cleanup_features, migrations.RunPython.noop),
        migrations.RunSQL(
            sql="ALTER TABLE core_plan DROP COLUMN IF EXISTS cosmetic_features",
            reverse_sql="ALTER TABLE core_plan ADD COLUMN IF NOT EXISTS cosmetic_features jsonb NULL DEFAULT '{}'::jsonb",
        ),
    ]


