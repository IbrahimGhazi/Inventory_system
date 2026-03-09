"""
signals.py
──────────
Registers post_save / post_delete handlers for every model in REGISTRY.

One generic handler pair covers all models — no per-model boilerplate.
Adding a new model to serializers.REGISTRY is all that's needed here.

Exceptions are always swallowed so the local app never crashes because
of a sync error.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.apps import apps

from .serializers import REGISTRY, REGISTRY_MAP
from .engine import push_instance, delete_from_supabase


def _connect_all():
    """
    Dynamically connect one save + one delete handler per registered model.
    Called once from SyncConfig.ready().
    """
    for spec in REGISTRY:
        try:
            model = spec.get_model()
        except Exception:
            continue  # app not ready yet — skip gracefully

        # Close over spec in the lambdas
        def make_save_handler(s):
            def handler(sender, instance, **kwargs):
                try:
                    push_instance(instance)
                except Exception:
                    pass  # never crash the save
            return handler

        def make_delete_handler(s):
            def handler(sender, instance, **kwargs):
                try:
                    delete_from_supabase(s, instance.pk)
                except Exception:
                    pass  # never crash the delete
            return handler

        post_save.connect(make_save_handler(spec), sender=model, weak=False)
        post_delete.connect(make_delete_handler(spec), sender=model, weak=False)

    # Special case: after a Payment save/delete, also re-sync the parent Customer
    # so that cached balance fields stay in sync on Supabase.
    from accounts.models import Payment, Customer
    from .serializers import REGISTRY_MAP

    customer_spec = REGISTRY_MAP.get(("accounts", "Customer"))

    if customer_spec:
        def on_payment_change(sender, instance, **kwargs):
            try:
                push_instance(instance.customer)
            except Exception:
                pass

        post_save.connect(on_payment_change, sender=Payment, weak=False)
        post_delete.connect(on_payment_change, sender=Payment, weak=False)

    # Same for Invoice — syncing an invoice should re-sync its Customer balance
    from invoice.models import Invoice
    def on_invoice_change(sender, instance, **kwargs):
        try:
            if instance.customer_id:
                from accounts.models import Customer
                cust = Customer.objects.filter(pk=instance.customer_id).first()
                if cust:
                    push_instance(cust)
        except Exception:
            pass

    post_save.connect(on_invoice_change, sender=Invoice, weak=False)
    post_delete.connect(on_invoice_change, sender=Invoice, weak=False)
