from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('integration', '0002_initial')]

    operations = [
        migrations.CreateModel(
            name='MirthChannel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('name', models.CharField(max_length=120)),
                ('source_system', models.CharField(max_length=120)),
                ('protocol', models.CharField(choices=[('hl7', 'HL7 v2'), ('fhir', 'FHIR')], default='hl7', max_length=20)),
                ('direction', models.CharField(choices=[('inbound', 'Inbound'), ('outbound', 'Outbound')], default='inbound', max_length=20)),
                ('mirth_base_url', models.URLField(blank=True)),
                ('channel_id', models.CharField(blank=True, max_length=120)),
                ('status', models.CharField(choices=[('active', 'Active'), ('paused', 'Paused'), ('error', 'Error')], default='active', max_length=20)),
                ('last_health_check', models.DateTimeField(blank=True, null=True)),
                ('last_message_at', models.DateTimeField(blank=True, null=True)),
                ('error_count', models.PositiveIntegerField(default=0)),
                ('settings', models.JSONField(blank=True, default=dict)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mirth_channels', to='integration.integrationclient')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mirth_channels', to='tenants.tenant')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.AddConstraint(
            model_name='mirthchannel',
            constraint=models.UniqueConstraint(fields=('tenant', 'name'), name='unique_mirth_channel_per_tenant'),
        ),
    ]