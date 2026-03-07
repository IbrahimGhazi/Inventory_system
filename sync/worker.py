"""
worker.py – Background thread that:
  1. Flushes PendingSync rows (failed/offline operations).
  2. Runs a full sync once per hour to catch anything missed.

Started automatically by SyncConfig.ready() when SUPABASE_SYNC_ENABLED=True.
"""
import threading
import logging
import time

logger = logging.getLogger('sync')

RETRY_INTERVAL  = 60     # seconds between pending-sync flush attempts
FULL_SYNC_EVERY = 3600   # seconds between full syncs (1 hour)

_thread = None


def _flush_pending():
    """Try to process all PendingSync rows."""
    try:
        from sync.models import PendingSync
        from django.apps import apps

        pending = list(PendingSync.objects.order_by('created_at')[:200])
        if not pending:
            return

        logger.info('Flushing %d pending sync(s)...', len(pending))
        from sync.supabase_sync import get_client
        client = get_client()

        for entry in pending:
            try:
                if entry.operation == PendingSync.DELETE:
                    client.table(entry.table_name).delete().eq('id', entry.record_id).execute()
                    entry.delete()

                elif entry.operation == PendingSync.UPSERT:
                    # Re-fetch the object from local DB and re-sync it
                    if entry.app_label and entry.model_name and entry.local_pk:
                        model = apps.get_model(entry.app_label, entry.model_name)
                        obj   = model.objects.filter(pk=entry.local_pk).first()
                        if obj is None:
                            # Object was deleted locally – remove pending upsert
                            entry.delete()
                            continue

                        # Import the correct sync function
                        from sync import supabase_sync as ss
                        fn_name = f'sync_{entry.model_name.lower()}'
                        fn = getattr(ss, fn_name, None)
                        if fn:
                            fn(obj)
                        entry.delete()
                    else:
                        entry.delete()   # Can't retry without model info

            except Exception as e:
                entry.attempts  += 1
                entry.last_error = str(e)[:500]
                if entry.attempts >= 20:
                    logger.error('Dropping %s after 20 attempts: %s', entry, e)
                    entry.delete()
                else:
                    entry.save(update_fields=['attempts', 'last_error'])

    except Exception as e:
        logger.error('_flush_pending error: %s', e)


def _worker_loop():
    last_full_sync = 0

    while True:
        try:
            _flush_pending()

            now = time.time()
            if now - last_full_sync >= FULL_SYNC_EVERY:
                from sync.supabase_sync import sync_all_data
                sync_all_data()
                last_full_sync = time.time()

        except Exception as e:
            logger.error('Worker loop error: %s', e)

        time.sleep(RETRY_INTERVAL)


def start():get_client()
    """Spawn the background worker daemon thread (called once at startup)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _thread = threading.Thread(target=_worker_loop, name='supabase-sync-worker', daemon=True)
    _thread.start()
    logger.info('Supabase sync worker started.')
