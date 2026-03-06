from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Template filter to access a dictionary item by key.
    Usage: {{ dict|get_item:some_key }}
    """
    if dictionary and key in dictionary:
        return dictionary[key]
    return None
