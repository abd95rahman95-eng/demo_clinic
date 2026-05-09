import logging
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from .models import Patient, Visit, UserProfile, VisitAttachment, ToothCondition, Notification, Clinic
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from .forms import PatientForm, NurseVisitForm, DoctorVisitForm, VisitAttachmentForm, SignupRequestForm
from .specialty_lists import (
    get_quick_picks,
    get_nursing_fields,
    get_specialty_medical_fields,
    build_field_specs,
    COMMON_MEDICAL_FIELDS,
    FIELD_LABELS,
    get_ai_system_prompt,
)
import json as _json_specs
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from datetime import date


# -----------------------------------------------------------------------------
# Arabic search normalization
#   - all alef variants (أ، إ، آ، ٱ) are folded to plain ا
#   - spaces removed
#   - some invisible RTL/joiner marks stripped
# So "إبراهيم" "ابراهيم" "أبراهيم" "اب راهيم" all match each other.
# -----------------------------------------------------------------------------
_ARABIC_NORMALIZE_MAP = str.maketrans({
    'أ': 'ا',
    'إ': 'ا',
    'آ': 'ا',
    'ٱ': 'ا',
    ' ': '',
    '‌': '',  # zero-width non-joiner
    '‏': '',  # right-to-left mark
    '‎': '',  # left-to-right mark
})


def _normalize_arabic(text):
    if not text:
        return ''
    return str(text).translate(_ARABIC_NORMALIZE_MAP)



@login_required(login_url='login')
def dashboard_view(request):
    profile = UserProfile.objects.get(user=request.user)

    patients = Patient.objects.filter(clinic=profile.clinic).order_by('-id')
    completed_visits = Visit.objects.filter(
        patient__clinic=profile.clinic,
        status='doctor_completed'
    ).order_by('-created_at')

    pending_visits = Visit.objects.filter(
        clinic=profile.clinic,
        status='nurse_draft'
    ).order_by('-created_at')

    if is_doctor(request.user):
        user_role = 'طبيب'
    elif is_nurse(request.user):
        user_role = 'ممرضة'
    else:
        user_role = '—'

    today = date.today()

    # Today's bookings (visits whose follow_up appointment is today)
    todays_bookings = Visit.objects.filter(
        patient__clinic=profile.clinic,
        follow_up_date__date=today
    ).order_by('follow_up_date')

    days_ar = {
        'Monday': 'الاثنين',
        'Tuesday': 'الثلاثاء',
        'Wednesday': 'الأربعاء',
        'Thursday': 'الخميس',
        'Friday': 'الجمعة',
        'Saturday': 'السبت',
        'Sunday': 'الأحد',
    }

    months_ar = {
        1: 'كانون الثاني',
        2: 'شباط',
        3: 'آذار',
        4: 'نيسان',
        5: 'أيار',
        6: 'حزيران',
        7: 'تموز',
        8: 'آب',
        9: 'أيلول',
        10: 'تشرين الأول',
        11: 'تشرين الثاني',
        12: 'كانون الأول',
    }

    formatted_date = f"{days_ar[today.strftime('%A')]} {today.day} {months_ar[today.month]}"

    return render(request, 'patients/dashboard.html', {
        'clinic_name': profile.clinic.name,
        'user_role': user_role,
        'formatted_date': formatted_date,
        'patients_count': patients.count(),
        'visits_count': completed_visits.count(),
        'pending_visits_count': pending_visits.count(),
        'next_patient_visit': pending_visits.order_by('created_at').first(),
        'latest_patients': patients[:5],
        'latest_completed_visits': completed_visits[:5],
        'latest_pending_visits': pending_visits.order_by('created_at')[:5],
        'todays_bookings': todays_bookings,
        'todays_bookings_count': todays_bookings.count(),
        'is_doctor': is_doctor(request.user),
        'is_nurse': is_nurse(request.user),
    })

@login_required(login_url='login')
def nurse_create_visit(request, patient_id):

    profile = UserProfile.objects.get(user=request.user)
    patient = get_object_or_404(Patient, id=patient_id)

    if patient.clinic != profile.clinic:
        return redirect('patient_list')

    existing = Visit.objects.filter(
        patient=patient,
        status='nurse_draft'
    ).exists()

    if existing:
        messages.warning(request, "يوجد زيارة معلقة بالفعل لهذا المريض")
        return redirect('patient_detail', id=patient.id)

    if request.method == 'POST':
        form = NurseVisitForm(request.POST, clinic=profile.clinic)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.patient = patient
            visit.clinic = profile.clinic
            visit.created_by = request.user
            visit.status = 'nurse_draft'
            visit.save()

            messages.success(request, "تم حفظ البيانات التمريضية وإرسالها للطبيب")
            return redirect('patient_list')
    else:
        form = NurseVisitForm(clinic=profile.clinic)

    vitals_specs = build_field_specs(get_nursing_fields(profile.clinic.specialty))

    return render(request, 'patients/nurse_create_visit.html', {
        'form': form,
        'patient': patient,
        'vitals_specs': vitals_specs,
        'quick_picks': get_quick_picks(profile.clinic.specialty),
        'is_nurse_view': is_nurse(request.user),
    })

@login_required(login_url='login')
def doctor_pending_visits(request):
    if not is_doctor(request.user):
        return redirect('patient_list')

    profile = UserProfile.objects.get(user=request.user)

    visits = Visit.objects.filter(
        clinic=profile.clinic,
        assigned_doctor=request.user,
        status='nurse_draft'
    ).order_by('created_at')

    return render(request, 'patients/doctor_pending_visits.html', {
        'visits': visits,
    })

@login_required(login_url='login')
def waiting_list(request):
    if not is_nurse(request.user):
        return redirect('dashboard')

    profile = UserProfile.objects.get(user=request.user)

    visits = Visit.objects.filter(
        clinic=profile.clinic,
        status='nurse_draft'
    ).order_by('created_at')

    waiting_items = []
    for index, visit in enumerate(visits, start=1):
        waiting_items.append({
            'queue_number': index,
            'visit': visit,
        })

    return render(request, 'patients/waiting_list.html', {
        'waiting_items': waiting_items,
    })

@login_required(login_url='login')
def doctor_complete_visit(request, visit_id):
    if not is_doctor(request.user):
        return redirect('patient_list')

    profile = UserProfile.objects.get(user=request.user)
    clinic = profile.clinic
    visit = get_object_or_404(Visit, id=visit_id, clinic=clinic)
    attachment_form = VisitAttachmentForm()
    if visit.clinic != profile.clinic:
        return redirect('patient_list')

    if visit.assigned_doctor != request.user:
        return redirect('doctor_pending_visits')

    # Doctor only edits MEDICAL fields here. Nurse fields are read-only and
    # edited via the same nurse_edit_visit page (Edit button on this screen).
    if request.method == 'POST':
        form = DoctorVisitForm(
            request.POST, instance=visit,
            specialty=clinic.specialty, exclude_nurse=True,
        )
        attachment_form = VisitAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.status = 'doctor_completed'
            visit.save()
            messages.success(request, "تم إكمال الزيارة بنجاح")

            if attachment_form.is_valid() and attachment_form.cleaned_data.get('image'):
                # Hard cap: max 2 attachments per visit (UI hides the input
                # when full, this is the server-side guard).
                if visit.attachments.count() >= 2:
                    messages.warning(
                        request,
                        "لا يمكن إضافة أكثر من مرفقين لهذه الزيارة."
                    )
                else:
                    attachment = attachment_form.save(commit=False)
                    attachment.visit = visit
                    attachment.uploaded_by = request.user
                    attachment.save()
                    messages.success(request, "تم إضافة المرفق بنجاح")

            return redirect('patient_detail', id=visit.patient.id)

    else:
        form = DoctorVisitForm(
            instance=visit,
            specialty=clinic.specialty, exclude_nurse=True,
        )

    # Dental chart: inherit previous visit's chart on first open
    dental_data = {}
    if clinic.specialty == 'dentistry':
        _ensure_dental_chart_inherited(visit)
        dental_data = _dental_conditions_dict(visit)

    vitals_specs = build_field_specs(get_nursing_fields(clinic.specialty))
    medical_specs = build_field_specs(
        ['history_of_present_illness', 'clinical_examination']
        + get_specialty_medical_fields(clinic.specialty)
        + COMMON_MEDICAL_FIELDS
    )

    return render(request, 'patients/doctor_complete_visit.html', {
        'form': form,
        'visit': visit,
        'attachment_form': attachment_form,
        'clinic': clinic,
        'specialty': clinic.specialty,
        'quick_picks': get_quick_picks(clinic.specialty),
        'vitals_specs': vitals_specs,
        'medical_specs': medical_specs,
        # Pass the dict directly — the template's json_script filter handles encoding.
        'dental_data': dental_data,
        'dental_choices': {
            'conditions': ToothCondition.CONDITION_CHOICES,
            'surfaces':   ToothCondition.SURFACE_CHOICES,
        },
    })

@login_required(login_url='login')
def add_patient(request):
    profile = UserProfile.objects.get(user=request.user)

    if request.method == 'POST':
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save(commit=False)
            patient.clinic = profile.clinic
            patient.save()

            messages.success(request, "تمت إضافة المريض بنجاح")
            return redirect('patient_detail', id=patient.id)
    else:
        form = PatientForm()

    return render(request, 'patients/add_patient.html', {'form': form})

@login_required(login_url='login')
def patient_list(request):
    profile = UserProfile.objects.get(user=request.user)
    query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', '').strip()

    all_patients = Patient.objects.filter(clinic=profile.clinic).order_by('-id')
    filtered_patients = all_patients

    if query:
        filtered_patients = filtered_patients.filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(file_number__icontains=query)
        )

    patients_with_status_all = []
    for patient in filtered_patients:
        last_visit = Visit.objects.filter(patient=patient).order_by('-created_at').first()

        if last_visit:
            if last_visit.status == 'nurse_draft':
                visit_status = 'معلقة'
                card_class = 'patient-pending'
                status_key = 'pending'
            elif last_visit.status == 'doctor_completed':
                visit_status = 'مكتملة'
                card_class = 'patient-completed'
                status_key = 'completed'
            else:
                visit_status = 'غير معروفة'
                card_class = 'patient-none'
                status_key = 'none'
        else:
            visit_status = 'لا توجد زيارات'
            card_class = 'patient-none'
            status_key = 'none'

        patients_with_status_all.append({
            'patient': patient,
            'visit_status': visit_status,
            'card_class': card_class,
            'status_key': status_key,
        })

    if filter_type:
        patients_with_status_all = [
            item for item in patients_with_status_all
            if item['status_key'] == filter_type
        ]

    paginator = Paginator(patients_with_status_all, 5)
    page_number = request.GET.get('page')
    patients_with_status = paginator.get_page(page_number)

    return render(request, 'patients/patient_list.html', {
        'patients_with_status': patients_with_status,
        'query': query,
        'filter_type': filter_type,
        'total_patients': all_patients.count(),
        'results_count': len(patients_with_status_all),
    })

@login_required(login_url='login')
def patient_detail(request, id):
    profile = UserProfile.objects.get(user=request.user)
    patient = get_object_or_404(Patient, id=id)

    if patient.clinic != profile.clinic:
        return redirect('patient_list')

    pending_visit = Visit.objects.filter(
        patient=patient,
        status='nurse_draft'
    ).order_by('-created_at').first()

    visits = None
    sort_order = request.GET.get('sort', 'newest')

    if is_doctor(request.user):
        visits_query = Visit.objects.filter(
            patient=patient,
            status='doctor_completed'
        )
        if sort_order == 'oldest':
            visits = visits_query.order_by('created_at')
        else:
            visits = visits_query.order_by('-created_at')

    # ----- Per-specialty field manifest (drives both screen + print) -----
    specialty = patient.clinic.specialty

    # Vitals = optional vitals for this specialty.
    vitals_specs = build_field_specs(get_nursing_fields(specialty))

    # Nursing block = chief_complaint + nursing_notes (always shown if filled).
    nursing_text_specs = build_field_specs(['chief_complaint', 'nursing_notes'])

    # Medical block = history + clinical_examination + specialty fields + common
    medical_specs = build_field_specs(
        ['history_of_present_illness', 'clinical_examination']
        + get_specialty_medical_fields(specialty)
        + COMMON_MEDICAL_FIELDS
    )

    # Pre-filter "present vitals" per visit so the template can render the
    # wrapper conditionally without needing template-time gymnastics.
    def _attach_present_vitals(v):
        if v is None:
            return
        v.present_vitals = [
            {'name': f['name'], 'label': f['label'],
             'value': getattr(v, f['name'], '') or ''}
            for f in vitals_specs
            if getattr(v, f['name'], '')
        ]

    _attach_present_vitals(pending_visit)
    if visits is not None:
        for v in visits:
            _attach_present_vitals(v)

    return render(request, 'patients/patient_detail.html', {
        'patient': patient,
        'pending_visit': pending_visit,
        'visits': visits,
        'is_doctor': is_doctor(request.user),
        'is_nurse': is_nurse(request.user),
        'sort_order': sort_order,
        'clinic_name': profile.clinic.name,
        'specialty': specialty,
        'vitals_specs': vitals_specs,
        'nursing_text_specs': nursing_text_specs,
        'medical_specs': medical_specs,
    })


@login_required(login_url='login')
def add_visit(request, patient_id):
    if not is_doctor(request.user):
        return redirect('patient_list')

    profile = UserProfile.objects.get(user=request.user)
    patient = get_object_or_404(Patient, id=patient_id)

    if patient.clinic != profile.clinic:
        return redirect('patient_list')

    if request.method == 'POST':
        history = request.POST['history']
        diagnosis = request.POST['diagnosis']
        prescription = request.POST['prescription']
        notes = request.POST['notes']

        Visit.objects.create(
            patient=patient,
            history=history,
            diagnosis=diagnosis,
            prescription=prescription,
            notes=notes
        )

        return redirect('patient_detail', id=patient.id)

    return render(request, 'patients/add_visit.html', {'patient': patient})

@login_required(login_url='login')
def delete_patient(request, id):
    if not is_doctor(request.user):
        return redirect('patient_list')
    profile = UserProfile.objects.get(user=request.user)
    patient = get_object_or_404(Patient, id=id)

    # حماية: نفس العيادة فقط
    if patient.clinic != profile.clinic:
        return redirect('patient_list')

    if request.method == 'POST':
        patient.delete()
        messages.success(request, "تم حذف المريض بنجاح")
        return redirect('patient_list')

    return render(request, 'patients/confirm_delete.html', {'patient': patient})

@login_required(login_url='login')
def delete_visit(request, id):
    if not is_doctor(request.user):
        return redirect('patient_list')

    profile = UserProfile.objects.get(user=request.user)
    visit = get_object_or_404(Visit, id=id)

    if visit.clinic != profile.clinic:
        return redirect('patient_list')

    if visit.status != 'doctor_completed':
        messages.error(request, "لا يمكن حذف زيارة غير مكتملة.")
        return redirect('doctor_pending_visits')

    if request.method == 'POST':
        patient_id = visit.patient.id
        visit.delete()
        messages.success(request, "تم حذف الزيارة بنجاح")
        return redirect('patient_detail', id=patient_id)

    return render(request, 'patients/confirm_delete_visit.html', {
        'visit': visit,
    })

@login_required(login_url='login')
def edit_patient(request, id):
    profile = UserProfile.objects.get(user=request.user)
    patient = get_object_or_404(Patient, id=id)

    if patient.clinic != profile.clinic:
        return redirect('patient_list')

    if request.method == 'POST':
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل بيانات المريض بنجاح")
            return redirect('patient_detail', id=patient.id)
    else:
        form = PatientForm(instance=patient)

    return render(request, 'patients/edit_patient.html', {
        'form': form,
        'patient': patient,
    })

@login_required(login_url='login')
def edit_visit(request, id):
    if not is_doctor(request.user):
        return redirect('patient_list')

    profile = UserProfile.objects.get(user=request.user)
    visit = get_object_or_404(Visit, id=id)

    if visit.clinic != profile.clinic:
        return redirect('patient_list')

    if visit.status != 'doctor_completed':
        messages.error(request, "لا يمكن تعديل زيارة غير مكتملة.")
        return redirect('doctor_pending_visits')

    clinic = profile.clinic

    form = DoctorVisitForm(
        request.POST or None, instance=visit,
        specialty=clinic.specialty,
    )
    attachment_form = VisitAttachmentForm(
        request.POST or None, request.FILES or None
    )

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل الزيارة بنجاح")

            # Save a new attachment if the doctor selected one. Empty file
            # input is a no-op — keeps existing attachments untouched.
            if attachment_form.is_valid() and attachment_form.cleaned_data.get('image'):
                # Hard cap: max 2 attachments per visit.
                if visit.attachments.count() >= 2:
                    messages.warning(
                        request,
                        "لا يمكن إضافة أكثر من مرفقين لهذه الزيارة."
                    )
                else:
                    attachment = attachment_form.save(commit=False)
                    attachment.visit = visit
                    attachment.uploaded_by = request.user
                    attachment.save()
                    messages.success(request, "تم إضافة المرفق بنجاح")

            return redirect('patient_detail', id=visit.patient.id)

    dental_data = {}
    if clinic.specialty == 'dentistry':
        # Don't auto-copy on edit (visit is already completed); just show what's saved
        dental_data = _dental_conditions_dict(visit)

    vitals_specs = build_field_specs(get_nursing_fields(clinic.specialty))
    medical_specs = build_field_specs(
        ['history_of_present_illness', 'clinical_examination']
        + get_specialty_medical_fields(clinic.specialty)
        + COMMON_MEDICAL_FIELDS
    )

    return render(request, 'patients/edit_visit.html', {
        'form': form,
        'visit': visit,
        'clinic': clinic,
        'attachment_form': attachment_form,
        'specialty': clinic.specialty,
        'quick_picks': get_quick_picks(clinic.specialty),
        'vitals_specs': vitals_specs,
        'medical_specs': medical_specs,
        # Pass the dict directly — the template's json_script filter handles encoding.
        'dental_data': dental_data,
        'dental_choices': {
            'conditions': ToothCondition.CONDITION_CHOICES,
            'surfaces':   ToothCondition.SURFACE_CHOICES,
        },
    })

@login_required(login_url='login')
def nurse_edit_visit(request, id):
    """Edit nurse-draft data. Open to nurses AND to doctors — the doctor uses
    this same flow from the doctor_complete_visit page (Edit button) so there
    is one consistent place to edit nursing data."""
    if not (is_nurse(request.user) or is_doctor(request.user)):
        return redirect('patient_list')

    profile = UserProfile.objects.get(user=request.user)
    visit = get_object_or_404(Visit, id=id)

    # حماية
    if visit.patient.clinic != profile.clinic:
        return redirect('patient_list')

    # لا يسمح بالتعديل بعد إكمال الطبيب
    if visit.status != 'nurse_draft':
        return redirect('patient_detail', id=visit.patient.id)

    specialty = visit.clinic.specialty
    nursing_fields = get_nursing_fields(specialty)
    vitals_specs = build_field_specs(nursing_fields)

    # Where to send the user after save: doctors come back to the complete
    # screen so they can keep filling the medical section; nurses go to the
    # patient detail page as before.
    came_from_doctor = (
        request.GET.get('next') == 'complete'
        or request.POST.get('next') == 'complete'
        or is_doctor(request.user)
    )

    if request.method == 'POST':
        # Always save the always-shown text fields
        visit.chief_complaint = request.POST.get('chief_complaint', '')
        visit.nursing_notes   = request.POST.get('nursing_notes', '')
        # And only the vitals that are valid for this specialty
        for fname in nursing_fields:
            setattr(visit, fname, request.POST.get(fname, ''))

        visit.save()

        messages.success(request, "تم تعديل الزيارة التمريضية")
        if came_from_doctor and is_doctor(request.user):
            return redirect('doctor_complete_visit', visit_id=visit.id)
        return redirect('patient_detail', id=visit.patient.id)

    return render(request, 'patients/nurse_edit_visit.html', {
        'visit': visit,
        'vitals_specs': vitals_specs,
        'came_from_doctor': came_from_doctor and is_doctor(request.user),
        'quick_picks': get_quick_picks(specialty),
        'is_nurse_view': is_nurse(request.user),
    })

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)

        if user is not None:
            # تحقق مما إذا كان اشتراك العيادة نشطاً
            if hasattr(user, 'userprofile'):
                clinic = user.userprofile.clinic
                if not clinic.is_active_subscription:
                    return render(request, 'patients/login.html', {'error': 'انتهت صلاحية اشتراك العيادة أو الفترة التجريبية. يرجى التواصل مع الإدارة لتجديد الاشتراك.'})

            login(request, user)
            
            # احتفظ بجلسة واحدة نشطة لكل مستخدم
            from django.contrib.sessions.models import Session
            from django.utils import timezone
            
            current_session_key = request.session.session_key
            for session in Session.objects.filter(expire_date__gte=timezone.now()):
                if session.session_key != current_session_key:
                    data = session.get_decoded()
                    if str(data.get('_auth_user_id', '')) == str(user.id):
                        session.delete()
                        
            return redirect('dashboard')
        else:
            return render(request, 'patients/login.html', {'error': 'اسم المستخدم أو كلمة المرور غير صحيحة'})

    return render(request, 'patients/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def is_doctor(user):
    return user.groups.filter(name='Doctor').exists()

def is_nurse(user):
    return user.groups.filter(name='Nurse').exists()

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


def signup_request_view(request):
    # NOTE: The notification email is sent automatically by the
    # `notify_new_signup_request` post_save signal in patients/signals.py.
    # Don't re-send it from here or recipients will get two emails per
    # signup with slightly different formats.
    if request.method == "POST":
        form = SignupRequestForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, "patients/signup_success.html")
    else:
        form = SignupRequestForm()

    return render(request, "patients/signup_request.html", {"form": form})

def pricing_view(request):
    return render(request, "patients/pricing.html")


# -----------------------------------------------------------------------------
# Account management — change password + view subscription status
# -----------------------------------------------------------------------------
@login_required(login_url='login')
def account_management(request):
    """Single page where the doctor / nurse can change their password and
    review the clinic's subscription status (renewal date, days left, how to
    renew via the pricing page)."""
    from django.contrib.auth import update_session_auth_hash
    from datetime import timedelta as _td

    profile = None
    clinic  = None
    try:
        profile = request.user.userprofile
        clinic  = profile.clinic
    except UserProfile.DoesNotExist:
        pass

    password_message = None
    password_error   = None
    if request.method == 'POST' and request.POST.get('action') == 'change_password':
        current   = request.POST.get('current_password', '')
        new1      = request.POST.get('new_password', '')
        new2      = request.POST.get('new_password_confirm', '')

        if not request.user.check_password(current):
            password_error = 'كلمة المرور الحالية غير صحيحة.'
        elif not new1 or len(new1) < 6:
            password_error = 'كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل.'
        elif new1 != new2:
            password_error = 'كلمتا المرور الجديدتان غير متطابقتين.'
        else:
            request.user.set_password(new1)
            request.user.save()
            update_session_auth_hash(request, request.user)  # keep logged in
            password_message = 'تم تغيير كلمة المرور بنجاح.'

    # Subscription status snapshot (for display).
    sub_status = {
        'is_active': False,
        'kind': None,             # 'trial' | 'subscription' | None
        'end_date': None,
        'days_left': 0,
        'period_label': '',
    }
    if clinic:
        from datetime import date as _date
        today = _date.today()
        # Trial first
        if clinic.trial_start and today <= clinic.trial_start + _td(days=30):
            sub_status['is_active'] = True
            sub_status['kind']      = 'trial'
            sub_status['end_date']  = clinic.trial_start + _td(days=30)
            sub_status['days_left'] = (sub_status['end_date'] - today).days
            sub_status['period_label'] = 'فترة تجريبية (30 يوماً)'
        elif clinic.subscription_start and clinic.subscription_period:
            if clinic.subscription_period == '1_month':
                end = clinic.subscription_start + _td(days=30)
                sub_status['period_label'] = 'اشتراك شهري'
            elif clinic.subscription_period == '1_year':
                end = clinic.subscription_start + _td(days=365)
                sub_status['period_label'] = 'اشتراك سنوي'
            else:
                end = None
            if end and today <= end:
                sub_status['is_active'] = True
                sub_status['kind']      = 'subscription'
                sub_status['end_date']  = end
                sub_status['days_left'] = (end - today).days
            else:
                sub_status['end_date']  = end

    return render(request, 'patients/account_management.html', {
        'profile': profile,
        'clinic':  clinic,
        'sub_status': sub_status,
        'password_message': password_message,
        'password_error':   password_error,
    })


# -----------------------------------------------------------------------------
# Contact-us page
# -----------------------------------------------------------------------------
def contact_us(request):
    """Static contact-us page. Shown to authenticated and anonymous users —
    we don't gate it behind login because the navbar dropdown links here and
    a logged-out visitor on the login page can't be in this view anyway."""
    return render(request, 'patients/contact_us.html')


@login_required(login_url='login')
@require_POST
def delete_visit_attachment(request, attachment_id):
    """Remove a single VisitAttachment. Open to doctors and nurses inside
    the same clinic. The file on disk is deleted as part of the cascade
    via the model's ImageField storage — Django handles that.

    Redirects back to the page the user came from when possible
    (doctor_complete_visit / edit_visit / patient_detail) so the user
    keeps their flow without a manual back-button."""
    if not (is_doctor(request.user) or is_nurse(request.user)):
        return redirect('dashboard')

    profile = UserProfile.objects.get(user=request.user)
    attachment = get_object_or_404(
        VisitAttachment,
        id=attachment_id,
        visit__clinic=profile.clinic,
    )
    visit = attachment.visit

    # Remove the underlying image file from storage so we don't leave
    # orphaned bytes on disk after the row is deleted.
    try:
        if attachment.image and attachment.image.name:
            attachment.image.delete(save=False)
    except Exception:
        # Storage hiccup shouldn't prevent the DB row from being removed.
        pass
    attachment.delete()
    messages.success(request, "تم حذف المرفق بنجاح")

    # Decide where to send the user back.
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url:
        return redirect(next_url)

    if visit.status == 'nurse_draft' and is_doctor(request.user) and visit.assigned_doctor_id == request.user.id:
        return redirect('doctor_complete_visit', visit_id=visit.id)
    if visit.status == 'doctor_completed' and is_doctor(request.user):
        return redirect('edit_visit', id=visit.id)
    return redirect('patient_detail', id=visit.patient.id)


# -----------------------------------------------------------------------------
# Notifications
# -----------------------------------------------------------------------------
def _notifications_for_clinic_qs(clinic):
    """All notifications visible to this clinic — broadcasts + ones
    explicitly targeted at it. Newest first.
    """
    return Notification.objects.filter(
        Q(target_clinic__isnull=True) | Q(target_clinic=clinic)
    ).order_by('-created_at')


@login_required(login_url='login')
@require_POST
def notifications_mark_all_read(request):
    """Mark every notification visible to the current clinic as read.
    Triggered by clicking "تم القراءة" / opening the bell, depending on
    the UI flow chosen on the front-end. Idempotent."""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'no_clinic'}, status=400)

    clinic = profile.clinic
    qs = _notifications_for_clinic_qs(clinic).exclude(read_by_clinics=clinic)
    updated = 0
    for notif in qs:
        notif.read_by_clinics.add(clinic)
        updated += 1
    return JsonResponse({'ok': True, 'updated': updated})


@login_required(login_url='login')
def notifications_list(request):
    """Full-page list of notifications for the current clinic. Linked
    from the bell footer ("عرض كل الإشعارات")."""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        return redirect('dashboard')

    clinic = profile.clinic
    qs = _notifications_for_clinic_qs(clinic)[:200]
    read_ids = set(
        Notification.objects.filter(
            id__in=[n.id for n in qs],
            read_by_clinics=clinic,
        ).values_list('id', flat=True)
    )
    items = []
    for n in qs:
        items.append({
            'id': n.id,
            'title': n.title,
            'body': n.body,
            'url': n.url,
            'created_at': n.created_at.strftime('%Y-%m-%d %H:%M'),
            'read': n.id in read_ids,
        })
    return render(request, 'patients/notifications_list.html', {
        'notifications': items,
    })


def _is_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required(login_url='login')
def notifications_admin(request):
    """Staff-only page to broadcast a notification to all clinics or to
    a specific clinic, plus list / edit / delete existing notifications.

    Permission: only Django superusers / staff can use this page.
    Non-staff users are redirected to the dashboard.
    """
    if not _is_staff(request.user):
        return redirect('dashboard')

    sent_msg = None
    error = None

    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        body  = (request.POST.get('body') or '').strip()
        url   = (request.POST.get('url') or '').strip()
        target = (request.POST.get('target_clinic_id') or '').strip()

        if not title:
            error = 'العنوان مطلوب.'
        else:
            target_clinic = None
            if target:
                try:
                    target_id = int(target)
                    target_clinic = Clinic.objects.filter(id=target_id).first()
                    if target_clinic is None:
                        error = f'العيادة رقم {target_id} غير موجودة.'
                except ValueError:
                    error = 'معرف العيادة يجب أن يكون رقماً صحيحاً.'
            if not error:
                Notification.objects.create(
                    title=title, body=body, url=url,
                    target_clinic=target_clinic,
                )
                messages.success(request, 'تم إرسال الإشعار بنجاح.')
                return redirect('notifications_admin')

    # Filter the list shown below the form: optional ?q=... search by
    # title/body, and optional ?clinic=<id> (or 'broadcast') filter.
    list_q = (request.GET.get('q') or '').strip()
    list_clinic = (request.GET.get('clinic') or '').strip()

    # Build the list as a plain Python list of dicts up-front rather than
    # passing a queryset through to the template. This sidesteps any
    # template-time DB access (e.g. lazy FK lookups on a NULL-able
    # target_clinic when select_related is involved with the Meta
    # ordering on a freshly migrated SQLite DB), and makes the rendering
    # path bulletproof — a single bad row can't blow up the whole page.
    base_qs = Notification.objects.select_related('target_clinic')
    if list_q:
        base_qs = base_qs.filter(Q(title__icontains=list_q) | Q(body__icontains=list_q))
    if list_clinic == 'broadcast':
        base_qs = base_qs.filter(target_clinic__isnull=True)
    elif list_clinic:
        try:
            base_qs = base_qs.filter(target_clinic_id=int(list_clinic))
        except ValueError:
            pass

    # Explicit ordering on the ID is a safe tiebreaker — order_by('-created_at')
    # alone with rapidly-created rows can have equal timestamps which leads
    # paginator + select_related to occasionally repeat or skip rows.
    base_qs = base_qs.order_by('-created_at', '-id')

    paginator = Paginator(base_qs, 20)
    page = paginator.get_page(request.GET.get('page'))

    notif_rows = []
    for n in page.object_list:
        try:
            target_label = ''
            if n.target_clinic_id:
                tc = n.target_clinic
                if tc is not None:
                    if tc.clinic_number:
                        target_label = f"{tc.name} (#{tc.clinic_number})"
                    else:
                        target_label = tc.name
            notif_rows.append({
                'id':           n.id,
                'title':        n.title or '',
                'body':         n.body or '',
                'created_at':   n.created_at,
                'is_broadcast': n.target_clinic_id is None,
                'target_label': target_label,
            })
        except Exception:
            # Never let a single bad row break the whole list.
            log = logging.getLogger(__name__)
            log.exception("notifications_admin: failed to render notification id=%s", getattr(n, 'id', '?'))

    return render(request, 'patients/notifications_admin.html', {
        'sent_msg': sent_msg,
        'error': error,
        'notifications_page': page,
        'notif_rows': notif_rows,
        'list_q': list_q,
        'list_clinic': list_clinic,
    })


@login_required(login_url='login')
def notification_edit(request, id):
    """Staff-only — edit an existing notification (title, body, url,
    target clinic). After saving, the unread state is reset for that
    notification so all targeted clinics see the update."""
    if not _is_staff(request.user):
        return redirect('dashboard')

    notif = get_object_or_404(Notification, id=id)
    error = None

    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        body  = (request.POST.get('body') or '').strip()
        url   = (request.POST.get('url') or '').strip()
        target = (request.POST.get('target_clinic_id') or '').strip()
        reset_reads = request.POST.get('reset_reads') == 'on'

        if not title:
            error = 'العنوان مطلوب.'
        else:
            target_clinic = None
            if target:
                try:
                    target_id = int(target)
                    target_clinic = Clinic.objects.filter(id=target_id).first()
                    if target_clinic is None:
                        error = f'العيادة رقم {target_id} غير موجودة.'
                except ValueError:
                    error = 'معرف العيادة يجب أن يكون رقماً صحيحاً.'
            if not error:
                notif.title = title
                notif.body = body
                notif.url = url
                notif.target_clinic = target_clinic
                notif.save()
                if reset_reads:
                    notif.read_by_clinics.clear()
                messages.success(request, 'تم تعديل الإشعار بنجاح.')
                return redirect('notifications_admin')

    return render(request, 'patients/notification_edit.html', {
        'notification': notif,
        'error': error,
    })


@login_required(login_url='login')
@require_POST
def notification_delete(request, id):
    """Staff-only — delete a notification entirely (it disappears from
    every clinic's bell)."""
    if not _is_staff(request.user):
        return redirect('dashboard')

    notif = get_object_or_404(Notification, id=id)
    notif.delete()
    messages.success(request, 'تم حذف الإشعار.')
    return redirect('notifications_admin')


@login_required(login_url='login')
def notifications_clinic_search_api(request):
    """Staff-only autocomplete used by the admin form's clinic search
    box. Returns up to 10 clinics matching the query (clinic name OR
    clinic_number). Each result has {id, label} ready to plug into a
    typeahead dropdown."""
    if not _is_staff(request.user):
        return JsonResponse({'results': []}, status=403)

    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse({'results': []})

    qs = Clinic.objects.all()
    # Try clinic_number first (admins commonly know the number) then
    # fall back to a name contains lookup so partial typing works.
    try:
        num = int(q)
        qs = qs.filter(Q(clinic_number=num) | Q(name__icontains=q))
    except ValueError:
        qs = qs.filter(name__icontains=q)

    qs = qs.order_by('clinic_number', 'name')[:10]
    results = [
        {
            'id': c.id,
            'clinic_number': c.clinic_number,
            'name': c.name,
            'label': f"{c.name} (#{c.clinic_number})" if c.clinic_number else c.name,
        }
        for c in qs
    ]
    return JsonResponse({'results': results})


@login_required(login_url='login')
def clear_appointment(request, visit_id):
    """Mark a follow-up appointment as done by clearing follow_up_date.
    Available to both doctors and nurses for visits in their clinic.
    """
    if not (is_doctor(request.user) or is_nurse(request.user)):
        return redirect('dashboard')

    profile = UserProfile.objects.get(user=request.user)
    visit = get_object_or_404(Visit, id=visit_id, patient__clinic=profile.clinic)

    if request.method == 'POST':
        visit.follow_up_date = None
        visit.save(update_fields=['follow_up_date', 'updated_at'])
        messages.success(request, "تم وضع الموعد كمنجز وإزالته من حجوزات اليوم")

    return redirect('dashboard')


# -----------------------------------------------------------------------------
# Live patient search API (used by the navbar search-as-you-type)
# Returns up to 8 matches as JSON.
# Matching is space-insensitive and alef-insensitive (see _normalize_arabic).
# -----------------------------------------------------------------------------
@login_required(login_url='login')
def patient_search_api(request):
    profile = UserProfile.objects.get(user=request.user)
    raw_q = request.GET.get('q', '').strip()
    if not raw_q:
        return JsonResponse({'results': []})

    nq = _normalize_arabic(raw_q).lower()
    if not nq:
        return JsonResponse({'results': []})

    patients = Patient.objects.filter(clinic=profile.clinic).order_by('-id')

    results = []
    for p in patients:
        name_n  = _normalize_arabic(p.name).lower()
        phone_n = _normalize_arabic(p.phone).lower()
        file_n  = _normalize_arabic(p.file_number).lower()
        if nq in name_n or nq in phone_n or nq in file_n:
            results.append({
                'id': p.id,
                'name': p.name,
                'phone': p.phone or '',
                'file_number': p.file_number or '',
            })
            if len(results) >= 8:
                break
    return JsonResponse({'results': results})


# -----------------------------------------------------------------------------
# Dental chart support
# -----------------------------------------------------------------------------
import json as _json


def _ensure_dental_chart_inherited(visit):
    """If the visit has no tooth conditions yet, copy them from this patient's
    most recent OTHER visit. Idempotent — safe to call repeatedly."""
    if visit.tooth_conditions.exists():
        return
    previous = (
        Visit.objects
        .filter(patient=visit.patient)
        .exclude(pk=visit.pk)
        .order_by('-created_at')
        .first()
    )
    if not previous:
        return
    prev_conditions = previous.tooth_conditions.all()
    if not prev_conditions:
        return
    ToothCondition.objects.bulk_create([
        ToothCondition(
            visit=visit,
            tooth_number=c.tooth_number,
            surface=c.surface,
            condition=c.condition,
            note=c.note,
        )
        for c in prev_conditions
    ])


def _dental_conditions_dict(visit):
    """Return current visit's tooth conditions as {"tooth-surface": condition}."""
    return {
        f"{c.tooth_number}-{c.surface}": {
            'condition': c.condition,
            'note': c.note,
        }
        for c in visit.tooth_conditions.all()
    }


@login_required(login_url='login')
@require_POST
def update_tooth_condition(request, visit_id):
    """AJAX endpoint — create/update/delete a single tooth-surface condition.
    Body (JSON): {"tooth_number": "11", "surface": "O", "condition": "caries", "note": ""}
    To clear a surface, send "condition": "" (empty string) — the row is deleted.
    """
    if not is_doctor(request.user):
        return JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)

    profile = UserProfile.objects.get(user=request.user)
    visit = get_object_or_404(Visit, id=visit_id, clinic=profile.clinic)

    try:
        payload = _json.loads(request.body.decode('utf-8') or '{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    tooth = str(payload.get('tooth_number', '')).strip()
    surface = str(payload.get('surface', 'whole')).strip() or 'whole'
    condition = str(payload.get('condition', '')).strip()
    note = str(payload.get('note', '') or '')[:200]

    valid_teeth = {t for t, _ in ToothCondition.TOOTH_CHOICES}
    valid_surfaces = {s for s, _ in ToothCondition.SURFACE_CHOICES}
    valid_conditions = {c for c, _ in ToothCondition.CONDITION_CHOICES}

    if tooth not in valid_teeth:
        return JsonResponse({'ok': False, 'error': 'bad_tooth'}, status=400)
    if surface not in valid_surfaces:
        return JsonResponse({'ok': False, 'error': 'bad_surface'}, status=400)

    # Empty condition → delete the row (clear that surface)
    if condition == '':
        ToothCondition.objects.filter(
            visit=visit, tooth_number=tooth, surface=surface
        ).delete()
        return JsonResponse({'ok': True, 'cleared': True})

    if condition not in valid_conditions:
        return JsonResponse({'ok': False, 'error': 'bad_condition'}, status=400)

    obj, _ = ToothCondition.objects.update_or_create(
        visit=visit,
        tooth_number=tooth,
        surface=surface,
        defaults={'condition': condition, 'note': note},
    )
    return JsonResponse({
        'ok': True,
        'tooth_number': obj.tooth_number,
        'surface': obj.surface,
        'condition': obj.condition,
        'note': obj.note,
    })


# -----------------------------------------------------------------------------
# AI medical assistance (Claude)
# -----------------------------------------------------------------------------
# POST /patients/api/visits/<visit_id>/ai-assist/
#   Body: ignored (uses server-side visit data).
#   Returns: { ok: bool, suggestions: str, error?: str }
#
# The view assembles a structured snapshot of the visit (vitals + nurse text +
# specialty-specific medical fields), wraps it with a specialty-aware system
# prompt from specialty_lists.SPECIALTY_AI_PROMPTS, and calls Claude.
# Dentistry has no prompt configured → endpoint returns 400 with a clear msg.
# -----------------------------------------------------------------------------
def _refund_ai_usage(clinic, source):
    """Undo a consume_ai_usage() call when the underlying API fails so the
    doctor isn't billed for a usage that produced no output."""
    if source == 'daily' and (clinic.ai_daily_used or 0) > 0:
        clinic.ai_daily_used = clinic.ai_daily_used - 1
        clinic.save(update_fields=['ai_daily_used'])
    elif source == 'credit':
        clinic.ai_credits = (clinic.ai_credits or 0) + 1
        clinic.save(update_fields=['ai_credits'])


def _build_visit_snapshot(visit):
    """Compose an Arabic, label:value snapshot of every populated field on
    the visit, ordered roughly the same way the doctor sees the form.

    Two design goals:
      1. Every non-empty field is forwarded to Claude (no silent drops),
         so the assistant has the complete picture. Date fields are
         formatted explicitly so they're not ambiguous.
      2. We append a separate "تم توفيره مسبقاً" (already provided)
         summary listing tests/imaging the doctor or nurse has already
         entered. The system prompt instructs the model to NOT re-suggest
         anything in that list — fixes the user's complaint that the
         assistant kept asking for data already present.
    """
    specialty = visit.clinic.specialty

    # Build an ordered, deduplicated field list. Anything else with a
    # value gets appended at the end so we never silently drop fields
    # that aren't in the manifests above (defense-in-depth).
    field_order = (
        ['chief_complaint', 'nursing_notes']
        + get_nursing_fields(specialty)
        + ['history_of_present_illness', 'clinical_examination']
        + get_specialty_medical_fields(specialty)
        + COMMON_MEDICAL_FIELDS
    )

    # Date-typed fields that need explicit string formatting.
    DATE_FIELDS = {'follow_up_date', 'last_menstrual_period'}

    # Fields that count as "tests already provided/requested" — used to
    # build the explicit list at the bottom of the snapshot.
    TEST_FIELDS = {
        'lab_requests', 'lab_results',
        'imaging_requests', 'imaging_results',
        'ecg_results', 'xray_findings',
        'ultrasound_notes', 'CT_MRI_findings',
        'neurological_examination', 'skin_examination',
    }

    lines = []
    p = visit.patient
    # Patient demographics — useful for differential weighting.
    lines.append(f"المريض: {p.name} | العمر: {p.age} | الجنس: {p.get_gender_display()}")
    lines.append(f"نوع الزيارة: {visit.get_visit_type_display()}")
    lines.append("")
    lines.append("بيانات الزيارة:")

    seen = set()
    provided_tests = []

    def _format_value(fname, val):
        """Render a field value safely. Dates → ISO; else str()."""
        if val is None:
            return ''
        if fname in DATE_FIELDS:
            try:
                if hasattr(val, 'strftime'):
                    if fname == 'follow_up_date':
                        return val.strftime('%Y-%m-%d %H:%M')
                    return val.strftime('%Y-%m-%d')
            except Exception:
                pass
        return str(val)

    def _is_empty(val):
        """Treat None, empty string, and whitespace-only strings as empty.
        We KEEP zero values (e.g. pain_scale = 0) because they are
        meaningful clinical data."""
        if val is None:
            return True
        if isinstance(val, str) and not val.strip():
            return True
        return False

    # 1) Manifest-driven fields, in the same order the doctor saw them.
    for fname in field_order:
        if fname in seen:
            continue
        seen.add(fname)
        val = getattr(visit, fname, '')
        if _is_empty(val):
            continue
        label = FIELD_LABELS.get(fname, fname)
        rendered = _format_value(fname, val)
        lines.append(f"- {label}: {rendered}")
        if fname in TEST_FIELDS:
            provided_tests.append(label)

    # 2) Defense-in-depth — anything else on the model that's set and
    # has a known label, but didn't appear in the manifests, is still
    # forwarded so the AI never says "you forgot to include X".
    for fname, label in FIELD_LABELS.items():
        if fname in seen:
            continue
        val = getattr(visit, fname, None)
        if _is_empty(val):
            continue
        seen.add(fname)
        rendered = _format_value(fname, val)
        lines.append(f"- {label}: {rendered}")
        if fname in TEST_FIELDS:
            provided_tests.append(label)

    # 3) Explicit list of tests/imaging already provided so the model can
    # reliably skip them when suggesting required investigations.
    if provided_tests:
        lines.append("")
        lines.append("ملاحظة للنموذج — الفحوصات التي تم طلبها أو إدخال نتائجها مسبقاً (لا تكررها في اقتراحاتك):")
        for label in provided_tests:
            lines.append(f"  • {label}")
    else:
        lines.append("")
        lines.append("ملاحظة للنموذج — لم يتم طلب أو إدخال أي فحوصات/صور بعد.")

    return "\n".join(lines)


@login_required(login_url='login')
@require_POST
def ai_medical_assistance(request, visit_id):
    if not is_doctor(request.user):
        return JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)

    profile = UserProfile.objects.get(user=request.user)
    visit = get_object_or_404(Visit, id=visit_id, clinic=profile.clinic)

    specialty = visit.clinic.specialty
    system_prompt = get_ai_system_prompt(specialty)
    if not system_prompt:
        # Dentistry (or any future specialty without a prompt configured).
        return JsonResponse(
            {'ok': False,
             'error': 'المساعد الذكي غير متاح لهذا التخصص.'},
            status=400,
        )

    # ── Enforce per-clinic usage quota ────────────────────────────────
    # Three free uses per calendar day; once exhausted, fall back to
    # purchased credits. When both are zero, signal limit_reached so
    # the frontend can show the purchase popup.
    clinic = visit.clinic
    usage = clinic.consume_ai_usage()
    if not usage['ok']:
        return JsonResponse(
            {
                'ok': False,
                'limit_reached': True,
                'daily_limit': clinic.AI_DAILY_FREE_LIMIT,
                'daily_remaining': usage['daily_remaining'],
                'credits_remaining': usage['credits_remaining'],
                'error': (
                    'لقد استنفدت التحليلات المجانية لهذا اليوم ولا يوجد رصيد '
                    'مشترى متاح. يمكنك شراء المزيد من التحليلات للاستمرار في '
                    'استخدام المساعد الذكي.'
                ),
            },
            status=402,
        )

    from django.conf import settings as _settings
    api_key = getattr(_settings, 'ANTHROPIC_API_KEY', '') or os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        # We already consumed a usage above — refund it before returning
        # the error so the doctor isn't penalised for a server misconfig.
        _refund_ai_usage(clinic, usage['source'])
        return JsonResponse(
            {'ok': False,
             'error': 'لم يتم ضبط مفتاح Claude API. أضف ANTHROPIC_API_KEY إلى ملف .env.'},
            status=500,
        )

    snapshot = _build_visit_snapshot(visit)
    user_msg = (
        "فيما يلي بيانات زيارة طبية جُمعت من قِبل الطبيب والممرض. "
        "قم بتحليل البيانات واقتراح التشخيص التفريقي وخطة الفحوصات والعلاج "
        "وأي تنبيهات حمراء، بحسب التخصص.\n\n"
        + snapshot
    )

    # Use stdlib urllib so we don't add a runtime dependency. Anthropic's
    # Messages API accepts a plain JSON POST.
    import urllib.request as _ureq
    import urllib.error as _uerr

    payload = _json.dumps({
        "model": "claude-sonnet-4-5",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_msg},
        ],
    }).encode('utf-8')

    req = _ureq.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with _ureq.urlopen(req, timeout=60) as resp:
            body = resp.read().decode('utf-8')
            data = _json.loads(body)
    except _uerr.HTTPError as e:
        try:
            err_body = e.read().decode('utf-8', errors='replace')
        except Exception:
            err_body = str(e)
        _refund_ai_usage(clinic, usage['source'])
        return JsonResponse(            {'ok': False, 'error': f'Claude API error ({e.code}): {err_body[:500]}'},
            status=502,
        )
    except Exception as e:
        _refund_ai_usage(clinic, usage['source'])
        return JsonResponse(
            {'ok': False, 'error': f'تعذر الاتصال بـ Claude: {e}'},
            status=502,
        )

    # Extract text from the Messages API response shape.
    try:
        parts = data.get('content', []) or []
        text_chunks = [p.get('text', '') for p in parts if p.get('type') == 'text']
        suggestions = "\n".join(t for t in text_chunks if t).strip()
    except Exception:
        suggestions = ''

    if not suggestions:
        _refund_ai_usage(clinic, usage['source'])
        return JsonResponse(
            {'ok': False, 'error': 'لم يتم إرجاع اقتراحات من النموذج.'},
            status=502,
        )

    # Persist the generated suggestions on the visit so the doctor can
    # review them later without spending another usage.
    from django.utils import timezone as _tz
    visit.ai_suggestions = suggestions
    visit.ai_generated_at = _tz.now()
    visit.save(update_fields=['ai_suggestions', 'ai_generated_at', 'updated_at'])

    # Re-read fresh remaining counters from the now-saved clinic state.
    clinic.refresh_from_db(fields=['ai_daily_used', 'ai_credits', 'ai_last_reset'])
    return JsonResponse({
        'ok': True,
        'suggestions': suggestions,
        'source': usage['source'],
        'daily_limit': clinic.AI_DAILY_FREE_LIMIT,
        'daily_remaining': clinic.ai_daily_remaining,
        'credits_remaining': clinic.ai_credits or 0,
    })

# end of views.py
