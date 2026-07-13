from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_auditlog_tenant'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditlog',
            name='severity',
            field=models.CharField(
                max_length=20,
                choices=[('info', 'Info'), ('warning', 'Warning'), ('urgent', 'Urgent')],
                default='info',
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='title',
            field=models.CharField(max_length=255, blank=True),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='actor',
            field=models.CharField(max_length=255, blank=True),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='is_verified',
            field=models.BooleanField(default=True, db_index=True),
        ),
    ]
