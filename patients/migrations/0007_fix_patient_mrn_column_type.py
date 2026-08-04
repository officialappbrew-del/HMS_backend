from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0006_alter_patient_address_alter_patient_genotype'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                -- The mrn column was originally created as an INTEGER with a CHECK (mrn >= 0)
                -- constraint (from PositiveIntegerField/AutoField), but the model defines it
                -- as CharField. Drop the integer CHECK constraint so PostgreSQL can convert
                -- the column type without trying to evaluate 'varchar >= 0'.
                ALTER TABLE patients_patient
                    DROP CONSTRAINT IF EXISTS patients_patient_mrn_check;

                -- Convert the column from integer to varchar(50).
                ALTER TABLE patients_patient
                    ALTER COLUMN mrn TYPE varchar(50) USING mrn::text;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
