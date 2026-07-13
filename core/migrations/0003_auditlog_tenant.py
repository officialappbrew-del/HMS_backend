from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0006_tenantuser_is_root_admin_and_more'),
        ('core', '0002_alter_auditlog_action_alter_auditlog_ip_address_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditlog',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='audit_logs',
                to='tenants.tenant',
            ),
        ),
    ]
