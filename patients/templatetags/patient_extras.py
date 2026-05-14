# patients/templatetags/patient_extras.py
import json as _json
from django import template
from django.forms.boundfield import BoundField

register = template.Library()


# Arabic weekday names — kept here so templates can format dates without
# routing through views. Matches the mapping used in views.dashboard_view.
_ARABIC_DAY_NAMES = {
    'Monday': 'الاثنين',
    'Tuesday': 'الثلاثاء',
    'Wednesday': 'الأربعاء',
    'Thursday': 'الخميس',
    'Friday': 'الجمعة',
    'Saturday': 'السبت',
    'Sunday': 'الأحد',
}


@register.filter(name='arabic_day')
def arabic_day(value):
    """Return the Arabic weekday for a date/datetime, or '' if value is None.

    Usage in template: {{ appt.scheduled_at|arabic_day }}
    """
    if not value:
        return ''
    try:
        return _ARABIC_DAY_NAMES.get(value.strftime('%A'), '')
    except Exception:
        return ''


@register.filter(name='format_prescription_items')
def format_prescription_items(raw):
    """Render the structured prescription JSON as a human-friendly multiline
    string like:
        paracetamol 500mg — 3 مرات يوم — 5 أيام (ملاحظات)
        amoxicillin 250mg — مرتين يومياً — أسبوع

    The doctor enters rows in the prescription_items field as a JSON array of
    {name, dose, frequency, duration, notes}. The previous patient_detail just
    dumped the raw JSON (showed "{name: ..., dose: ...}" to users) — this
    filter turns that into one line per drug. If the input isn't valid JSON
    (e.g. an old plain-text prescription) we return it unchanged."""
    if raw is None:
        return ''
    s = str(raw).strip()
    if not s:
        return ''
    try:
        parsed = _json.loads(s)
    except Exception:
        return s  # Not JSON — show as-is.
    if not isinstance(parsed, list):
        return s
    lines = []
    for row in parsed:
        if not isinstance(row, dict):
            continue
        name = (row.get('name') or '').strip()
        if not name:
            continue
        dose      = (row.get('dose') or '').strip()
        frequency = (row.get('frequency') or '').strip()
        duration  = (row.get('duration') or '').strip()
        notes     = (row.get('notes') or '').strip()
        # Build: "name dose" then any of frequency/duration separated by ' — '.
        head = (name + ' ' + dose).strip() if dose else name
        extras = [bit for bit in (frequency, duration) if bit]
        line = head
        if extras:
            line += ' — ' + ' — '.join(extras)
        if notes:
            line += ' (' + notes + ')'
        lines.append(line)
    return '\n'.join(lines)


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
