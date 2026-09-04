from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('emr', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='progressnote',
            name='template_data',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='progressnote',
            name='template_type',
            field=models.CharField(blank=True, max_length=80),
        ),
    ]