# patients/templatetags/patient_extras.py
from django import template
from django.forms.boundfield import BoundField

register = template.Library()


@register.filter(name='get_attr')
def get_attr(obj, name):
    """Return obj.<name> by attribute OR by dict key.

    Returns '' on missing keys/attrs so templates can guard cleanly with
    `{% if val %}` without raising.
    """
    if obj is None or not name:
        return ''
    try:
        if name in obj:
            value = obj[name]
            return '' if value is None else value
    except TypeError:
        pass
    value = getattr(obj, name, '')
    if value is None:
        return ''
    return value


@register.filter(name='form_field')
def form_field(form, name):
    """Return the BoundField for `name` on `form`, or None if missing."""
    if form is None or not name:
        return None
    try:
        return form[name]
    except KeyError:
        return None


@register.filter(name='is_bound_field')
def is_bound_field(value):
    return isinstance(value, BoundField)
