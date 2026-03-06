"""
PendingSync – stores operations that failed (offline) so they can be retried
when internet is restored.
"""
from django.db import models


class PendingSync(models.Model):
    """
    Queue entry for a sync operation that could not be completed (e.g. offline).

    operation  : 'upsert' or 'delete'
    table_name : Supabase table  (e.g. 'customers')
    record_id  : the Supabase row id  (string or int as str)
    app_label  : Django app  (e.g. 'accounts')  – used to re-fetch on retry
    model_name : Django model class name  (e.g. 'Customer')
    local_pk   : Django local PK  (used for upsert retries)
    """
    UPSERT = 'upsert'
    DELETE = 'delete'
    OPERATION_CHOICES = [(UPSERT, 'Upsert'), (DELETE, 'Delete')]

    operation  = models.CharField(max_length=10, choices=OPERATION_CHOICES)
    table_name = models.CharField(max_length=100)
    record_id  = models.CharField(max_length=200)      # Supabase row ID
    app_label  = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    local_pk   = models.CharField(max_length=100, blank=True)  # Django PK for retry
    created_at = models.DateTimeField(auto_now_add=True)
    attempts   = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Pending Sync'
        verbose_name_plural = 'Pending Syncs'

    def __str__(self):
        return f'{self.operation} {self.table_name}:{self.record_id}'
