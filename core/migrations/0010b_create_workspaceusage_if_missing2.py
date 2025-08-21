from django.db import migrations


SQL = r"""
CREATE TABLE IF NOT EXISTS core_workspaceusage (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    subscription_id uuid NOT NULL,
    period_start timestamp with time zone NOT NULL,
    period_end timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'core_workspaceusage_unique_period'
    ) THEN
        ALTER TABLE core_workspaceusage
        ADD CONSTRAINT core_workspaceusage_unique_period
        UNIQUE (workspace_id, period_start, period_end);
    END IF;
END
$$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010a_create_workspaceusage_if_missing'),
    ]

    operations = [
        migrations.RunSQL(sql=SQL, reverse_sql="""
            -- Not dropping table on reverse to avoid data loss
            SELECT 1;
        """),
    ]


