from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0005_visit_imaging_results_visit_lab_results'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='visit',
                    name='imaging_results',
                    field=models.TextField(blank=True),
                ),
            ],
        ),
    ]