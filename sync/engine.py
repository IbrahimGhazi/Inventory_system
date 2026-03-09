"""
engine.py
─────────
Core sync operations:

  push_instance(instance)          – upsert one model instance to Supabase
  delete_from_supabase(spec, pk)   – delete one row from Supabase
  flush_pending()                  – retry all PendingSync queue entries
  push_all()                       – full push of every table (initial sync / recovery)
  restore_all()                    – pull everything from Supabase into local DB

All network errors are caught and queued in PendingSync so the local app
never crashes due to connectivity issues.
"""
from __future__ import annotations

import logging
from django.db import transaction

from .supabase_client import is_enabled, batch_upsert, post_rows, delete_row
from .serializers import REGISTRY, REGISTRY_MAP, ModelSpec

logger = logging.getLogger("sync")


# ── pending queue helpers ──────────────────────────────────────────────────────

def _enqueue(operation: str, spec: ModelSpec, pk, error: str = "") -> None:
    """Write a failed operation to PendingSync so it can be retried later."""
    try:
        from sync.models import PendingSync
        PendingSync.objects.create(
            operation=operation,
            table_name=spec.table,
            record_id=str(pk),
            app_label=spec.app_label,
            model_name=spec.model_name,
            local_pk=str(pk),
            last_error=str(error)[:500],
        )
    except Exception as exc:
        logger.error("Failed to enqueue PendingSync: %s", exc)


# ── signal-driven helpers ──────────────────────────────────────────────────────

def push_instance(instance) -> None:
    """
    Upsert a single model instance to Supabase.
    Called from signals after every save.
    Does nothing if sync is disabled.
    """
    if not is_enabled():
        return

    model = type(instance)
    key = (model._meta.app_label, model.__name__)
    spec = REGISTRY_MAP.get(key)
    if spec is None:
        return  # model not registered for sync — silently skip

    try:
        row = spec.serializer(instance)
    except Exception as exc:
        logger.warning("Serialise failed %s pk=%s: %s", key, instance.pk, exc)
        return

    if not post_rows(spec.table, [row]):
        _enqueue("upsert", spec, instance.pk, "post failed")


def delete_from_supabase(spec: ModelSpec, pk) -> None:
    """
    Delete a row from Supabase by its primary key.
    Called from signals before/after every delete.
    """
    if not is_enabled():
        return
    if not delete_row(spec.table, pk):
        _enqueue("delete", spec, pk, "delete failed")


# ── pending queue flush ────────────────────────────────────────────────────────

def flush_pending() -> int:
    """
    Retry all rows in PendingSync.
    Returns the number of entries successfully resolved.
    """
    from sync.models import PendingSync
    from django.apps import apps

    pending = list(PendingSync.objects.order_by("created_at")[:500])
    if not pending:
        return 0

    logger.info("Flushing %d pending sync entries…", len(pending))
    resolved = 0

    for entry in pending:
        try:
            spec_key = (entry.app_label, entry.model_name)
            spec = REGISTRY_MAP.get(spec_key)

            if entry.operation == PendingSync.DELETE:
                if spec and delete_row(spec.table, entry.record_id):
                    entry.delete()
                    resolved += 1
                else:
                    raise RuntimeError("delete_row failed")

            elif entry.operation == PendingSync.UPSERT:
                if not (spec and entry.local_pk):
                    entry.delete()  # can't retry without model info
                    continue

                model = spec.get_model()
                obj = model.objects.filter(pk=entry.local_pk).first()
                if obj is None:
                    # object was deleted locally — remove stale upsert
                    entry.delete()
                    continue

                row = spec.serializer(obj)
                if post_rows(spec.table, [row]):
                    entry.delete()
                    resolved += 1
                else:
                    raise RuntimeError("post_rows failed on retry")

        except Exception as exc:
            entry.attempts += 1
            entry.last_error = str(exc)[:500]
            if entry.attempts >= 20:
                logger.error("Dropping PendingSync %s after 20 attempts: %s", entry, exc)
                entry.delete()
            else:
                entry.save(update_fields=["attempts", "last_error"])

    logger.info("Pending flush complete — resolved %d / %d", resolved, len(pending))
    return resolved


# ── full push ──────────────────────────────────────────────────────────────────

def push_all(wipe_first: bool = False) -> dict[str, int]:
    """
    Push every registered model to Supabase.

    wipe_first=True  : deletes all rows from each Supabase table before
                       inserting, giving a guaranteed clean slate.
    wipe_first=False : upserts only — safe to run repeatedly without data loss.

    Returns a dict of {table_name: rows_synced}.
    """
    if not is_enabled():
        logger.info("Supabase sync not enabled — skipping push_all.")
        return {}

    from .supabase_client import nuke_table

    results: dict[str, int] = {}

    for spec in REGISTRY:
        table = spec.table
        try:
            rows = spec.all_rows()
        except Exception as exc:
            logger.error("Could not serialise %s: %s", table, exc)
            results[table] = -1
            continue

        if wipe_first:
            ok = nuke_table(table)
            if not ok:
                logger.warning("Could not wipe %s — proceeding with upsert anyway", table)

        count = batch_upsert(table, rows)
        results[table] = count
        logger.info("Pushed %d / %d rows → %s", count, len(rows), table)

    logger.info("push_all complete.")
    return results


# ── full restore (pull) ────────────────────────────────────────────────────────

def restore_all() -> dict[str, int]:
    """
    Pull every registered table from Supabase and upsert into local SQLite.

    Uses update_or_create so it is safe to run on a populated database
    (existing rows are updated, missing rows are created).

    Returns a dict of {table_name: rows_restored}.
    """
    from .supabase_client import fetch_all_rows

    results: dict[str, int] = {}

    # Restore in the same dependency order as REGISTRY
    for spec in REGISTRY:
        table = spec.table
        logger.info("Restoring %s…", table)

        try:
            rows = fetch_all_rows(table)
        except Exception as exc:
            logger.error("fetch_all_rows %s failed: %s", table, exc)
            results[table] = -1
            continue

        if not rows:
            logger.info("  %s — no rows on Supabase", table)
            results[table] = 0
            continue

        model = spec.get_model()
        restored = 0
        errors = 0

        with transaction.atomic():
            for row in rows:
                try:
                    pk = row.get("id")
                    if pk is not None:
                        model.objects.update_or_create(id=pk, defaults=row)
                    else:
                        model.objects.create(**row)
                    restored += 1
                except Exception as exc:
                    errors += 1
                    logger.warning(
                        "  restore row failed %s id=%s: %s",
                        table, row.get("id"), exc,
                    )

        logger.info("  %s — restored %d rows (%d errors)", table, restored, errors)
        results[table] = restored

    logger.info("restore_all complete.")
    return results
