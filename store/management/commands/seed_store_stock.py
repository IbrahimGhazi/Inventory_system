from django.core.management.base import BaseCommand
from store.models import Item
from locations.models import Store, StoreStock


class Command(BaseCommand):
    help = 'Seed StoreStock from Item.stock values, assigning all to one default store'

    def add_arguments(self, parser):
        parser.add_argument('--store-id', type=int, required=True,
                            help='PK of the store to assign all existing stock to')

    def handle(self, *args, **options):
        store = Store.objects.get(pk=options['store_id'])
        created = updated = 0
        for item in Item.objects.filter(stock__gt=0):
            obj, new = StoreStock.objects.get_or_create(
                store=store, item=item,
                defaults={'quantity': item.stock}
            )
            if new:
                created += 1
            else:
                obj.quantity = item.stock
                obj.save(update_fields=['quantity'])
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(f'Done. Created: {created}, Updated: {updated}')
        )