"""
management/commands/sync_now.py
────────────────────────────────
Push all local data to Supabase immediately.

Usage:
    python manage.py sync_now            # upsert-only (safe, default)
    python manage.py sync_now --wipe     # wipe each Supabase table then re-insert
                                          # use this after clearing Supabase manually
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Push all local data to Supabase immediately"

    def add_arguments(self, parser):
        parser.add_argument(
            "--wipe",
            action="store_true",
            default=False,
            help="Delete all rows from each Supabase table before inserting "
                 "(clean-slate push). Use with care.",
        )

    def handle(self, *args, **options):
        from sync.engine import push_all

        wipe = options["wipe"]
        if wipe:
            self.stdout.write(self.style.WARNING(
                "⚠  --wipe flag set. All Supabase rows will be deleted before sync."
            ))

        self.stdout.write("Starting full push to Supabase…")
        results = push_all(wipe_first=wipe)

        self.stdout.write("\nResults:")
        total = 0
        for table, count in results.items():
            if count < 0:
                self.stdout.write(self.style.ERROR(f"  ✗  {table:<40} ERROR"))
            else:
                self.stdout.write(f"  ✓  {table:<40} {count} rows")
                total += count

        self.stdout.write(self.style.SUCCESS(f"\n✅ Sync complete — {total} rows pushed."))
