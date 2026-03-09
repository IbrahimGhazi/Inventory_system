"""
apps.py
───────
Wires everything together at Django startup.

  1. Imports signals → registers post_save/post_delete for all models
  2. Starts background worker if SUPABASE_SYNC_ENABLED=True
"""
from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sync"

    def ready(self) -> None:
        # Register all model signals
        from sync.signals import _connect_all
        _connect_all()

        # Start background worker on local machine only
        from django.conf import settings
        if getattr(settings, "SUPABASE_SYNC_ENABLED", False):
            try:
                from sync import worker
                worker.start()
            except Exception as exc:
                import logging
                logging.getLogger("sync").error(
                    "Could not start sync worker: %s", exc
                )
