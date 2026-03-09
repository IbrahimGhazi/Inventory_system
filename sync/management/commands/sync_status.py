"""
management/commands/sync_status.py
────────────────────────────────────
Shows a quick health dashboard comparing local SQLite row counts
against live Supabase row counts for every registered table.

Usage:
    python manage.py sync_status
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Compare local vs Supabase row counts for all registered tables"

    def handle(self, *args, **options):
        from sync.serializers import REGISTRY
        from sync.supabase_client import fetch_all_rows, is_enabled
        from sync.models import PendingSync

        if not is_enabled():
            self.stdout.write(self.style.WARNING(
                "⚠  SUPABASE_SYNC_ENABLED=False — Supabase counts will not be fetched."
            ))

        pending_count = PendingSync.objects.count()
        self.stdout.write(f"\nPending sync queue: {pending_count} entries\n")

        header = f"{'Table':<40} {'Local':>8} {'Supabase':>10} {'Status':>10}"
        self.stdout.write(header)
        self.stdout.write("─" * len(header))

        total_local = 0
        total_supa  = 0
        any_mismatch = False

        for spec in REGISTRY:
            model = spec.get_model()
            local_count = model.objects.count()
            total_local += local_count

            if is_enabled():
                try:
                    rows = fetch_all_rows(spec.table)
                    supa_count = len(rows)
                except Exception:
                    supa_count = -1
            else:
                supa_count = "—"

            if supa_count == -1:
                status = self.style.ERROR("ERROR")
            elif supa_count == "—":
                status = "—"
            elif local_count == supa_count:
                status = self.style.SUCCESS("✓ OK")
            else:
                status = self.style.WARNING(f"⚠ DIFF {local_count - supa_count:+d}")
                any_mismatch = True

            supa_str = str(supa_count) if supa_count != -1 else "ERROR"
            self.stdout.write(
                f"{spec.table:<40} {local_count:>8} {supa_str:>10}  {status}"
            )

            if isinstance(supa_count, int) and supa_count >= 0:
                total_supa += supa_count

        self.stdout.write("─" * len(header))
        self.stdout.write(f"{'TOTAL':<40} {total_local:>8} {total_supa:>10}\n")

        if pending_count:
            self.stdout.write(self.style.WARNING(
                f"⚠  {pending_count} operations are queued. "
                "Run `python manage.py sync_now` to flush them."
            ))
        elif any_mismatch:
            self.stdout.write(self.style.WARNING(
                "⚠  Row count mismatches detected. "
                "Run `python manage.py sync_now` to push missing rows."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("✅ All tables in sync."))
