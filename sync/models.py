# sync/models.py — unchanged from original
# PendingSync is the offline retry queue. Never synced to Supabase.

"""
PendingSync – stores operations that failed (offline) so they can be retried
when internet is restored.
"""
from django.db import models


class PendingSync(models.Model):
    UPSERT = 'upsert'
    DELETE = 'delete'
    OPERATION_CHOICES = [(UPSERT, 'Upsert'), (DELETE, 'Delete')]

    operation  = models.CharField(max_length=10, choices=OPERATION_CHOICES)
    table_name = models.CharField(max_length=100)
    record_id  = models.CharField(max_length=200)
    app_label  = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    local_pk   = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts   = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Pending Sync'
        verbose_name_plural = 'Pending Syncs'

    def __str__(self):
        return f'{self.operation} {self.table_name}:{self.record_id}'
