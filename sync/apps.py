from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sync"

    def ready(self):
        import sync.signals  # register signal handlers

        from django.conf import settings
        if getattr(settings, "SUPABASE_SYNC_ENABLED", False):
            try:
                from sync import worker
                worker.start()
            except Exception as e:
                import logging
                logging.getLogger("sync").error(
                    "Could not start sync worker: %s", e
                )