from .models import UserProfile, Visit

def clinic_role_context(request):
    if not request.user.is_authenticated:
        return {}

    role_name = ''
    clinic_name_global = ''
    pending_visits_badge = 0

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

    except UserProfile.DoesNotExist:
        clinic_name_global = ''

    return {
        'role_name': role_name,
        'clinic_name_global': clinic_name_global,
        'pending_visits_badge': pending_visits_badge,
    }