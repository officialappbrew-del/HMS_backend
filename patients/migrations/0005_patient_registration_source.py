from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('patients', '0004_rename_patients_pa_tenant__a6a3c7_idx_patients_pa_tenant__dd8881_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='registration_source',
            field=models.CharField(
                choices=[
                    ('self_service', 'Patient self-registration'),
                    ('staff_dashboard', 'Staff dashboard'),
                ],
                db_index=True,
                default='staff_dashboard',
                max_length=30,
            ),
        ),
    ]