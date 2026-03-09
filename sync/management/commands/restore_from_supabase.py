"""
management/commands/restore_from_supabase.py
─────────────────────────────────────────────
Pull all data from Supabase and load it into the local SQLite database.

Usage:
    python manage.py restore_from_supabase

Safe to run on a populated database — uses update_or_create so existing
rows are updated rather than duplicated.

Typical use-cases:
  - Setting up a new local machine from the cloud copy
  - Recovering a corrupted local database
  - Syncing a fresh Railway deployment from Supabase
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Pull all data from Supabase into the local database"

    def handle(self, *args, **options):
        from sync.engine import restore_all

        self.stdout.write("🚀 Starting restore from Supabase…\n")
        results = restore_all()

        self.stdout.write("\nResults:")
        total = 0
        for table, count in results.items():
            if count < 0:
                self.stdout.write(self.style.ERROR(f"  ✗  {table:<40} ERROR"))
            elif count == 0:
                self.stdout.write(self.style.WARNING(f"  –  {table:<40} 0 rows (empty on Supabase)"))
            else:
                self.stdout.write(f"  ✓  {table:<40} {count} rows")
                total += count

        self.stdout.write(self.style.SUCCESS(f"\n✅ Restore complete — {total} rows loaded."))
