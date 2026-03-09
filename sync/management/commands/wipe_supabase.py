"""
management/commands/wipe_supabase.py
─────────────────────────────────────
DELETE all rows from every registered Supabase table, then immediately
push all local data back up.

This is the "clean slate" command you use after manually clearing the
Supabase database — it rebuilds the cloud copy from your local SQLite.

Usage:
    python manage.py wipe_supabase             # dry-run by default (prints plan)
    python manage.py wipe_supabase --confirm   # actually runs the wipe + push

⚠  This is DESTRUCTIVE — all data currently on Supabase will be removed.
   Local SQLite data is never touched.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Wipe all Supabase tables and push fresh data from local SQLite"

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Actually perform the wipe. Without this flag the command "
                 "is a dry-run that only prints what it would do.",
        )

    def handle(self, *args, **options):
        from sync.serializers import REGISTRY
        from sync.supabase_client import is_enabled, nuke_table
        from sync.engine import push_all

        if not is_enabled():
            self.stdout.write(self.style.ERROR(
                "SUPABASE_SYNC_ENABLED is False — aborting. "
                "Set it to True in your .env / settings before running this command."
            ))
            return

        # Wipe in REVERSE registry order so children are deleted before parents.
        # e.g. Payments must be wiped before Customers (FK constraint).
        tables = [spec.table for spec in reversed(REGISTRY)]

        self.stdout.write("\nThis command will:")
        self.stdout.write(self.style.WARNING("  1. DELETE all rows from the following Supabase tables:"))
        for t in tables:
            self.stdout.write(f"       {t}")
        self.stdout.write(self.style.SUCCESS("  2. Re-push all local SQLite data to those tables.\n"))
        self.stdout.write("  Local SQLite data is NOT affected.\n")

        if not options["confirm"]:
            self.stdout.write(self.style.WARNING(
                "Dry-run only. Add --confirm to actually run.\n"
            ))
            return

        # ── Step 1: Wipe ──────────────────────────────────────────────────────
        self.stdout.write("Step 1/2 — Wiping Supabase tables…")
        wipe_errors = []
        for t in tables:
            ok = nuke_table(t)
            if ok:
                self.stdout.write(f"  ✓  wiped {t}")
            else:
                self.stdout.write(self.style.ERROR(f"  ✗  could not wipe {t}"))
                wipe_errors.append(t)

        if wipe_errors:
            self.stdout.write(self.style.WARNING(
                f"\n⚠  {len(wipe_errors)} table(s) could not be wiped. "
                "Will still attempt push — rows may end up duplicated for those tables."
            ))

        # ── Step 2: Push ──────────────────────────────────────────────────────
        self.stdout.write("\nStep 2/2 — Pushing local data to Supabase…")
        results = push_all(wipe_first=False)   # already wiped above

        self.stdout.write("\nResults:")
        total = 0
        for table, count in results.items():
            if count < 0:
                self.stdout.write(self.style.ERROR(f"  ✗  {table:<40} ERROR"))
            else:
                self.stdout.write(f"  ✓  {table:<40} {count} rows")
                total += count

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Done — Supabase rebuilt with {total} rows from local database."
        ))
