# Generated manually for adding name field to MetaLeadForm

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='metaleadform',
            name='name',
            field=models.CharField(blank=True, default='', help_text='Meta Lead Form Name/Title', max_length=500),
        ),
    ]