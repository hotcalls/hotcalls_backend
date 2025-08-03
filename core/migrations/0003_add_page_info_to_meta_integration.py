# Generated manually for adding page_name and page_picture_url to MetaIntegration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_add_name_to_meta_lead_form'),
    ]

    operations = [
        migrations.AddField(
            model_name='metaintegration',
            name='page_name',
            field=models.CharField(blank=True, default='', help_text='Meta Page Name', max_length=500),
        ),
        migrations.AddField(
            model_name='metaintegration',
            name='page_picture_url',
            field=models.URLField(blank=True, default='', help_text='Meta Page Profile Picture URL'),
        ),
    ]