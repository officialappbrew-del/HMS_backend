from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('patients', '0002_initial')]

    operations = [
        migrations.AddField(
            model_name='patient', name='merged_into',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='merged_sources', to='patients.patient'),
        ),
        migrations.AddField(
            model_name='patient', name='merged_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='patient', name='merged_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='patient_merges', to='tenants.tenantuser'),
        ),
        migrations.AddField(
            model_name='patient', name='merge_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddIndex(
            model_name='patient',
            index=models.Index(fields=['tenant', 'merged_into'], name='patients_pa_tenant__a6a3c7_idx'),
        ),
        migrations.CreateModel(
            name='PatientMerge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('merged_at', models.DateTimeField(auto_now_add=True)),
                ('unmerged_at', models.DateTimeField(blank=True, null=True)),
                ('reason', models.TextField()),
                ('status', models.CharField(choices=[('active', 'Active'), ('unmerged', 'Unmerged')], default='active', max_length=20)),
                ('moved_records', models.JSONField(default=list)),
                ('merged_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_patient_merge_records', to='tenants.tenantuser')),
                ('source_patient', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='merge_record', to='patients.patient')),
                ('survivor_patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='surviving_merges', to='patients.patient')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='patient_merges', to='tenants.tenant')),
                ('unmerged_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='unmerged_patient_records', to='tenants.tenantuser')),
            ],
            options={
                'ordering': ['-merged_at'],
                'indexes': [
                    models.Index(fields=['tenant', 'status'], name='patients_pa_tenant__0e1c23_idx'),
                    models.Index(fields=['survivor_patient', 'status'], name='patients_pa_survivo_5ce8b4_idx'),
                ],
            },
        ),
    ]