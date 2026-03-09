"""
management/commands/migrate_supabase.py
────────────────────────────────────────
Runs Django migrations against the Supabase database while keeping
sync signals completely silent.

Without this command, running `migrate --database=supabase` causes
the sync signals to fire for every row touched during migration,
flooding the log with 404 errors because the tables don't exist
in Supabase's PostgREST schema cache yet.

Usage:
    python manage.py migrate_supabase

After this completes, run:
    python manage.py wipe_supabase --confirm
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Run migrations against Supabase with sync signals disabled"

    def handle(self, *args, **options):
        # Temporarily disable sync so signals don't fire during migration
        from django.conf import settings
        original = getattr(settings, "SUPABASE_SYNC_ENABLED", False)
        settings.SUPABASE_SYNC_ENABLED = False

        self.stdout.write("Sync signals disabled for migration.")
        self.stdout.write("Running: manage.py migrate --database=supabase\n")

        try:
            call_command("migrate", database="supabase", verbosity=1)
            self.stdout.write(self.style.SUCCESS(
                "\n✅ Supabase schema created successfully."
                "\n   Now run:  python manage.py wipe_supabase --confirm"
            ))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"\n✗ Migration failed: {exc}"))
            raise
        finally:
            settings.SUPABASE_SYNC_ENABLED = original
            self.stdout.write("Sync signals restored.")
