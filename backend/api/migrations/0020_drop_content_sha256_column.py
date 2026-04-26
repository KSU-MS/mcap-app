from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0019_backgroundjob"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE api_mcaplog DROP COLUMN IF EXISTS content_sha256;",
            reverse_sql=(
                "ALTER TABLE api_mcaplog "
                "ADD COLUMN IF NOT EXISTS content_sha256 varchar(64) NULL;"
            ),
        ),
    ]
