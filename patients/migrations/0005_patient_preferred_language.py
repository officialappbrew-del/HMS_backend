from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('patients', '0004_patient_dnr_order_patient_dnr_order_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='preferred_language',
            field=models.CharField(blank=True, default='English', max_length=100),
        ),
    ]
