from django.db.models import Q

from .models import UserProfile, Visit, Notification


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
        clinic = profile.clinic
        clinic_name_global = clinic.name

        if request.user.groups.filter(name='Doctor').exists():
            pending_visits_badge = Visit.objects.filter(
                clinic=clinic,
                assigned_doctor=request.user,
                status='nurse_draft'
            ).count()

        # Notifications — DB-backed (Notification model). Each row in the
        # bell carries a `read` flag relative to this clinic. The navbar
        # template reads `recent_notifications` for the dropdown and
        # `notifications_badge` for the red counter.
        try:
            visible_qs = Notification.objects.filter(
                Q(target_clinic__isnull=True) | Q(target_clinic=clinic)
            ).order_by('-created_at')

            recent = list(visible_qs[:10])
            read_ids = set(
                Notification.objects.filter(
                    id__in=[n.id for n in recent],
                    read_by_clinics=clinic,
                ).values_list('id', flat=True)
            )
            recent_notifications = [
                {
                    'id':    n.id,
                    'title': n.title,
                    # The bell template uses `meta` for the secondary line
                    # (timestamp + body preview).
                    'meta':  _format_meta(n),
                    'url':   n.url or '#',
                    'read':  n.id in read_ids,
                }
                for n in recent
            ]
            notifications_badge = visible_qs.exclude(read_by_clinics=clinic).count()
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
    body = (notif.body or '').strip()
    when = notif.created_at.strftime('%Y-%m-%d %H:%M') if notif.created_at else ''
    if body and len(body) > 80:
        body = body[:80].rstrip() + '…'
    return f"{body} · {when}" if body else when
