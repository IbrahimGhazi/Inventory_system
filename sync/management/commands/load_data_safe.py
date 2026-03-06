"""
load_data_safe.py
=================
Loads data_dump.json while temporarily disconnecting handle_user_profile
so loaddata doesn't hit a UniqueViolation on accounts_profile.

Usage:
    python manage.py load_data_safe
    python manage.py load_data_safe --fixture myfile.json
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db.models.signals import post_save


class Command(BaseCommand):
    help = 'Safely load fixture data with profile auto-create signal disconnected'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fixture',
            default='data_dump.json',
            help='Fixture file to load (default: data_dump.json)',
        )

    def handle(self, *args, **options):
        fixture = options['fixture']

        from django.contrib.auth import get_user_model
        from accounts.signals import handle_user_profile

        User = get_user_model()

        # 1. Disconnect the auto-profile signal
        post_save.disconnect(handle_user_profile, sender=User)
        self.stdout.write('  ✓ Disconnected handle_user_profile signal')

        try:
            # 2. Flush existing data
            self.stdout.write('  Flushing database...')
            call_command('flush', '--no-input', verbosity=0)
            self.stdout.write('  ✓ Database flushed')

            # 3. Load the fixture
            self.stdout.write(f'  Loading {fixture} ...')
            call_command('loaddata', fixture, verbosity=1)
            self.stdout.write(self.style.SUCCESS(f'  ✓ {fixture} loaded successfully'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Failed: {e}'))
            raise

        finally:
            # 4. Always reconnect — even if load failed
            post_save.connect(handle_user_profile, sender=User)
            self.stdout.write('  ✓ Reconnected handle_user_profile signal')