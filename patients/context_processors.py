from .models import UserProfile, Visit
from . import notifications_store

def clinic_role_context(request):
    if not request.user.is_authenticated:
        return {}

    role_name = ''
    clinic_name_global = ''
    pending_visits_badge = 0
    recent_notifications = []
    notifications_badge = 0

    if request.user.groups.filter(name='Doctor').exists():
        role_name = 'طبيب'
    elif request.user.groups.filter(name='Nurse').exists():
        role_name = 'ممرضة'

    try:
        profile = request.user.userprofile
        clinic_name_global = profile.clinic.name

        if request.user.groups.filter(name='Doctor').exists():
            pending_visits_badge = Visit.objects.filter(
                clinic=profile.clinic,
                assigned_doctor=request.user,
                status='nurse_draft'
            ).count()

        # Notifications (JSON-backed store — see notifications_store.py).
        # Each row already carries a `read` flag relative to this clinic;
        # the navbar template reads `recent_notifications` for the bell
        # dropdown and `notifications_badge` for the red counter badge.
        clinic_id = profile.clinic.id
        try:
            raw = notifications_store.get_notifications_for_clinic(clinic_id, limit=10)
            recent_notifications = [
                {
                    'id':    n.get('id', ''),
                    'title': n.get('title', ''),
                    # The bell template uses `meta` for the secondary line
                    # (timestamp + body preview).
                    'meta':  _format_meta(n),
                    'url':   n.get('url') or '#',
                    'read':  bool(n.get('read')),
                }
                for n in raw
            ]
            notifications_badge = notifications_store.unread_count_for_clinic(clinic_id)
        except Exception:
            # Bell must never crash the page.
            recent_notifications = []
            notifications_badge = 0

    except UserProfile.DoesNotExist:
        clinic_name_global = ''

    return {
        'role_name': role_name,
        'clinic_name_global': clinic_name_global,
        'pending_visits_badge': pending_visits_badge,
        'recent_notifications': recent_notifications,
        'notifications_badge': notifications_badge,
    }


def _format_meta(notif):
    """Build the secondary "meta" line shown under each notification
    title in the bell dropdown — short body preview + timestamp."""
    body = (notif.get('body') or '').strip()
    when = (notif.get('created_at') or '').replace('T', ' ')
    if body and len(body) > 80:
        body = body[:80].rstrip() + '…'
    return f"{body} · {when}" if body else when