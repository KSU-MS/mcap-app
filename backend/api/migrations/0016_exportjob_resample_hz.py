from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0015_async_pipeline_and_exports"),
    ]

    operations = [
        migrations.AddField(
            model_name="exportjob",
            name="resample_hz",
            field=models.FloatField(default=20.0),
        ),
    ]
