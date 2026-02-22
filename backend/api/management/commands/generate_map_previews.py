from django.core.management.base import BaseCommand

from api.models import McapLog
from api.tasks import generate_map_preview


class Command(BaseCommand):
    help = "Queue map preview generation for logs missing map_preview_uri"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--sync", action="store_true", help="Generate previews synchronously"
        )

    def handle(self, *args, **options):
        qs = McapLog.objects.filter(lap_path__isnull=False).filter(
            map_preview_uri__isnull=True
        )
        limit = options["limit"]
        if limit and limit > 0:
            qs = qs[:limit]

        logs = list(qs)
        if not logs:
            self.stdout.write(
                self.style.SUCCESS("No logs need map preview generation.")
            )
            return

        queued = 0
        for log in logs:
            if options["sync"]:
                generate_map_preview(log.id)
            else:
                generate_map_preview.delay(log.id)
            queued += 1

        mode = "generated" if options["sync"] else "queued"
        self.stdout.write(
            self.style.SUCCESS(f"{mode.capitalize()} map previews for {queued} logs.")
        )
