from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('clinical', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='prescription',
            name='quantity',
            field=models.PositiveIntegerField(default=1),
        ),
    ]