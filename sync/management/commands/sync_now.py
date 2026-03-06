"""
Management command: python manage.py sync_now

Pushes ALL local data to Supabase immediately.
Use this after first setup or after a long offline period.
"""
from django.core.management.base import BaseCommand
from sync.supabase_sync import sync_all_data


class Command(BaseCommand):
    help = 'Push all local data to Supabase right now'

    def handle(self, *args, **options):
        self.stdout.write('Starting full sync to Supabase...')
        sync_all_data()
        self.stdout.write(self.style.SUCCESS('Sync complete!'))
