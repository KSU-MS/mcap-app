from django.db import migrations, models


def _normalize_list(values):
    if not isinstance(values, list):
        return []
    seen = set()
    normalized = []
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def backfill_freeform_metadata(apps, schema_editor):
    McapLog = apps.get_model("api", "McapLog")

    for log in (
        McapLog.objects.select_related("car", "driver", "event_type").all().iterator()
    ):
        cars = _normalize_list(getattr(log, "cars", []))
        drivers = _normalize_list(getattr(log, "drivers", []))
        event_types = _normalize_list(getattr(log, "event_types", []))
        locations = _normalize_list(getattr(log, "locations", []))

        if log.car_id and getattr(log, "car", None) and log.car.name:
            cars = _normalize_list(cars + [log.car.name])
        if log.driver_id and getattr(log, "driver", None) and log.driver.name:
            drivers = _normalize_list(drivers + [log.driver.name])
        if (
            log.event_type_id
            and getattr(log, "event_type", None)
            and log.event_type.name
        ):
            event_types = _normalize_list(event_types + [log.event_type.name])

        log.cars = cars
        log.drivers = drivers
        log.event_types = event_types
        log.locations = locations
        log.save(update_fields=["cars", "drivers", "event_types", "locations"])


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0011_mcaplog_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcaplog",
            name="cars",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="User-defined car labels for filtering",
            ),
        ),
        migrations.AddField(
            model_name="mcaplog",
            name="drivers",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="User-defined driver labels for filtering",
            ),
        ),
        migrations.AddField(
            model_name="mcaplog",
            name="event_types",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="User-defined event type labels for filtering",
            ),
        ),
        migrations.AddField(
            model_name="mcaplog",
            name="locations",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="User-defined location labels for filtering",
            ),
        ),
        migrations.RunPython(backfill_freeform_metadata, migrations.RunPython.noop),
    ]
