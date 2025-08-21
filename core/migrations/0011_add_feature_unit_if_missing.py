from django.db import migrations


SQL = r"""
ALTER TABLE core_feature
    ADD COLUMN IF NOT EXISTS unit varchar(20) NULL;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_workspaceusage_extra_call_minutes'),
    ]

    operations = [
        migrations.RunSQL(sql=SQL, reverse_sql="""
            -- Not removing column on reverse
            SELECT 1;
        """),
    ]


