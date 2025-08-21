from django.db import migrations


SQL = r"""
CREATE TABLE IF NOT EXISTS core_endpointfeature (
    id uuid PRIMARY KEY,
    feature_id uuid NOT NULL,
    route_name varchar(200) NOT NULL,
    http_method varchar(10) NOT NULL DEFAULT '*',
    created_at timestamp with time zone NOT NULL DEFAULT NOW(),
    updated_at timestamp with time zone NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'core_endpointfeature_feature_id_fk'
    ) THEN
        ALTER TABLE core_endpointfeature
        ADD CONSTRAINT core_endpointfeature_feature_id_fk
        FOREIGN KEY (feature_id)
        REFERENCES core_feature (id)
        DEFERRABLE INITIALLY DEFERRED;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'core_endpointfeature_unique_route_method'
    ) THEN
        ALTER TABLE core_endpointfeature
        ADD CONSTRAINT core_endpointfeature_unique_route_method
        UNIQUE (route_name, http_method);
    END IF;
END
$$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_add_plan_stripe_columns_if_missing'),
    ]

    operations = [
        migrations.RunSQL(sql=SQL, reverse_sql="""
            -- Do not drop table on reverse
            SELECT 1;
        """),
    ]


