from django.db import migrations

SQL = r"""
ALTER TABLE core_plan ADD COLUMN IF NOT EXISTS stripe_product_id varchar(255) NULL UNIQUE;
ALTER TABLE core_plan ADD COLUMN IF NOT EXISTS stripe_price_id_monthly varchar(255) NULL;
ALTER TABLE core_plan ADD COLUMN IF NOT EXISTS stripe_price_id_yearly varchar(255) NULL;
ALTER TABLE core_plan ADD COLUMN IF NOT EXISTS price_monthly numeric(10,2) NULL;
ALTER TABLE core_plan ADD COLUMN IF NOT EXISTS price_yearly numeric(10,2) NULL;
ALTER TABLE core_plan ADD COLUMN IF NOT EXISTS cosmetic_features jsonb NULL DEFAULT '{}'::jsonb;
ALTER TABLE core_plan ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT TRUE;
"""

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0011_add_feature_unit_if_missing'),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL,
            reverse_sql="""
            -- Not dropping columns on reverse
            SELECT 1;
            """,
        ),
    ]
