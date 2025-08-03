# Generated manually to extend page_picture_url field length

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_add_page_info_to_meta_integration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='metaintegration',
            name='page_picture_url',
            field=models.URLField(blank=True, default='', help_text='Meta Page Profile Picture URL', max_length=1000),
        ),
    ]