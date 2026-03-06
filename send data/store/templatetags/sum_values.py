# store/templatetags/sum_values.py
from django import template
from django.db.models import Sum

register = template.Library()

@register.filter(name='sum_values')
def sum_values(iterable, field_name):
    """
    Sum a numeric attribute/field across an iterable of objects.

    Usage in template:
      {% load sum_values %}
      {{ my_qs|sum_values:"stock_qty" }}

    Works with:
    - QuerySets (will try to use .aggregate for DB efficiency)
    - Plain Python lists of objects (uses getattr)
    - Lists/QuerySets of numbers (no field_name needed; pass empty string or the literal field name same as numbers)
    """
    if iterable is None:
        return 0

    # If it's a Django QuerySet and field_name provided, use DB aggregation (fast)
    try:
        # QuerySet has .aggregate and ._iterable_class (best-effort check)
        if hasattr(iterable, 'aggregate') and field_name:
            agg = iterable.aggregate(total=Sum(field_name))
            return agg.get('total') or 0
    except Exception:
        # fallback to python iteration if aggregate fails for any reason
        pass

    # For plain python iterables or when field_name not suitable:
    total = 0
    if field_name:
        for obj in iterable:
            try:
                val = getattr(obj, field_name)
            except Exception:
                # if it's a mapping
                try:
                    val = obj[field_name]
                except Exception:
                    val = 0
            try:
                total += float(val or 0)
            except Exception:
                # ignore non-numeric
                pass
    else:
        # Summing direct numeric values in iterable
        for v in iterable:
            try:
                total += float(v or 0)
            except Exception:
                pass

    # Return integer if it's integer-like
    if total.is_integer():
        return int(total)
    return total
