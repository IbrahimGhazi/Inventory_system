from django.core.management.base import BaseCommand
from sync.supabase_sync import restore_all_from_supabase


class Command(BaseCommand):

    help = "Restore all data from Supabase"

    def handle(self, *args, **kwargs):

        self.stdout.write("🚀 Starting Supabase restore")

        restore_all_from_supabase()

        self.stdout.write(self.style.SUCCESS("✅ Restore complete"))