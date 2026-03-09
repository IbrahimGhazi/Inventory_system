"""
worker.py
─────────
Background daemon thread that runs inside the local Django process.

Every RETRY_INTERVAL seconds  → flush PendingSync queue (retry failed ops)
Every FULL_SYNC_EVERY seconds → full push_all() to catch anything missed
                                 (e.g. rows saved while sync was disabled)

Started automatically by SyncConfig.ready() when SUPABASE_SYNC_ENABLED=True.
Only runs on the LOCAL machine — Railway does not need this worker because
Railway always has internet access and signals fire reliably there.
"""
import threading
import logging
import time

logger = logging.getLogger("sync")

RETRY_INTERVAL  = 60       # seconds between pending-queue flush attempts
FULL_SYNC_EVERY = 3_600    # seconds between full syncs (1 hour)

_thread: threading.Thread | None = None


def _worker_loop() -> None:
    last_full_sync = 0.0

    while True:
        try:
            # 1. Flush any queued failures
            from .engine import flush_pending
            flush_pending()

            # 2. Periodic full sync (catches anything signals missed)
            now = time.time()
            if now - last_full_sync >= FULL_SYNC_EVERY:
                from .engine import push_all
                push_all(wipe_first=False)   # upsert-only; safe to run anytime
                last_full_sync = time.time()

        except Exception as exc:
            logger.error("Sync worker loop error: %s", exc)

        time.sleep(RETRY_INTERVAL)


def start() -> None:
    """Spawn the background worker daemon (called once at app startup)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _thread = threading.Thread(
        target=_worker_loop,
        name="supabase-sync-worker",
        daemon=True,          # dies automatically when the main process exits
    )
    _thread.start()
    logger.info("Supabase sync worker started (retry every %ds, full sync every %ds).",
                RETRY_INTERVAL, FULL_SYNC_EVERY)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
