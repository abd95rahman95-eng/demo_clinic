import logging
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from .models import (
    Patient, Visit, UserProfile, VisitAttachment, ToothCondition, Notification,
    Clinic, Appointment,
    # Dental chart v2 (3D, mode-driven) data layer
    ToothStatus, TreatmentPlan, PlanStep, VisitProcedure, VisitPlanSnapshot,
    DENTAL_TOOTH_CHOICES, DENTAL_SURFACE_CHOICES, DENTAL_CONDITION_CHOICES,
    DENTAL_PROCEDURE_CHOICES,
)
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from .forms import PatientForm, NurseVisitForm, DoctorVisitForm, VisitAttachmentForm, SignupRequestForm, AppointmentForm
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

    # "زيارات الاستشارة" — visits the doctor saved with the "حفظ كاستشارة"
    # save mode. Half-completed, awaiting specialist / lab / imaging.
    consultation_visits = Visit.objects.filter(
        clinic=profile.clinic,
        status='consultation_pending'
    ).order_by('-updated_at')

    if is_doctor(request.user):
        user_role = 'طبيب'
    elif is_nurse(request.user):
        user_role = 'ممرضة'
    else:
        user_role = '—'

    today = date.today()

    # Today's bookings — unified list combining BOTH sources:
    #   1. Visit.follow_up_date == today  (legacy follow-up bookings tied to a Visit)
    #   2. Appointment.scheduled_at__date == today  (booked appointments via the
    #      "احجز موعد" button, which is the modern, Visit-independent flow)
    # Each entry is normalized to a dict with: kind, id, patient, time, kind_label.
    # The template uses `kind` to route the "تم" / "ادخال" buttons to the right
    # backend handler (visit follow-up clears follow_up_date, appointment marks
    # status='done').
    todays_bookings = []
    visit_followups_today = Visit.objects.filter(
        patient__clinic=profile.clinic,
        follow_up_date__date=today
    ).order_by('follow_up_date')
    for v in visit_followups_today:
        todays_bookings.append({
            'kind':       'visit',
            'id':         v.id,
            'patient':    v.patient,
            'time':       v.follow_up_date,
            'kind_label': 'مراجعة',
        })
    booked_today = Appointment.objects.filter(
        clinic=profile.clinic,
        scheduled_at__date=today,
        status='scheduled',
    ).order_by('scheduled_at')
    for a in booked_today:
        todays_bookings.append({
            'kind':       'appointment',
            'id':         a.id,
            'patient':    a.patient,
            'time':       a.scheduled_at,
            'kind_label': a.get_appt_type_display(),
        })
    # Single chronological ordering across both sources.
    todays_bookings.sort(key=lambda b: b['time'])

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

    # Week-ahead booking count for the calendar card preview badge.
    # Includes both real Appointments and Visit follow-ups (which now also
    # render on the calendar as "مراجعة").
    from datetime import timedelta as _td
    week_start = today
    week_end = today + _td(days=7)
    upcoming_appointments_count = (
        Appointment.objects.filter(
            clinic=profile.clinic,
            scheduled_at__date__gte=week_start,
            scheduled_at__date__lt=week_end,
            status='scheduled',
        ).count()
        + Visit.objects.filter(
            patient__clinic=profile.clinic,
            follow_up_date__date__gte=week_start,
            follow_up_date__date__lt=week_end,
        ).count()
    )

    return render(request, 'patients/dashboard.html', {
        'clinic_name': profile.clinic.name,
        'user_role': user_role,
        'formatted_date': formatted_date,
        'patients_count': patients.count(),
        'visits_count': completed_visits.count(),
        'pending_visits_count': pending_visits.count(),
        'consultation_visits_count': consultation_visits.count(),
        'consultation_visits': consultation_visits[:5],
        'upcoming_appointments_count': upcoming_appointments_count,
        'next_patient_visit': pending_visits.order_by('created_at').first(),
        'latest_patients': patients[:5],
        'latest_completed_visits': completed_visits[:5],
        'latest_pending_visits': pending_visits.order_by('created_at')[:5],
        'todays_bookings': todays_bookings,
        'todays_bookings_count': len(todays_bookings),
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
def doctor_consultation_visits(request):
    """Dedicated page for consultation_pending visits — visits the doctor
    has marked as needing a referral / additional work. Reuses the pending-
    visits card layout but shows days-since-consultation and doctor_notes
    only (the dentist already moved past the nurse-side fields).
    """
    if not is_doctor(request.user):
        return redirect('patient_list')

    profile = UserProfile.objects.get(user=request.user)
    visits_qs = Visit.objects.filter(
        clinic=profile.clinic,
        status='consultation_pending',
    ).order_by('updated_at')

    today = date.today()
    rows = []
    for v in visits_qs:
        sent_at = (v.updated_at or v.created_at)
        days = (today - sent_at.date()).days if sent_at else 0
        rows.append({
            'visit': v,
            'days_since': days,
        })

    return render(request, 'patients/doctor_consultation_visits.html', {
        'rows': rows,
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
            # Three save modes, controlled by the `save_mode` hidden input
            # set on the chosen submit button:
            #   ''                = حفظ (default — visit fully completed)
            #   'print_rx'        = حفظ + طباعة الوصفة (same as default but
            #                       redirects to the A5 print page after save)
            #   'consultation'    = حفظ كاستشارة (status = consultation_pending,
            #                       half-completed, awaiting referral)
            save_mode = (request.POST.get('save_mode') or '').strip()
            if save_mode == 'consultation':
                visit.status = 'consultation_pending'
            else:
                visit.status = 'doctor_completed'
            visit.save()
            if save_mode == 'consultation':
                messages.success(request, "تم حفظ الزيارة كاستشارة (قيد الانتظار).")
            elif save_mode == 'print_rx':
                messages.success(request, "تم حفظ الزيارة. سيتم فتح الوصفة للطباعة.")
            else:
                messages.success(request, "تم إكمال الزيارة بنجاح")

            # ── Multi-file upload ────────────────────────────────────────
            # The template renders one camera input + one gallery input.
            # Each can carry multiple files (HTML5 `multiple`), and the
            # backend caps the total at 2 attachments per visit.
            # We pull files from BOTH fields manually since Django's
            # ClearableFileInput only captures the first file via the
            # ModelForm; getlist() returns all of them.
            uploaded_files = []
            for field_name in ('image', 'image_gallery'):
                uploaded_files.extend(request.FILES.getlist(field_name))

            remaining_slots = max(0, 2 - visit.attachments.count())
            if uploaded_files and remaining_slots == 0:
                messages.warning(
                    request,
                    "لا يمكن إضافة أكثر من مرفقين لهذه الزيارة."
                )
            else:
                added = 0
                for f in uploaded_files[:remaining_slots]:
                    attachment = VisitAttachment(
                        visit=visit,
                        image=f,
                        uploaded_by=request.user,
                    )
                    attachment.save()
                    added += 1
                if added:
                    messages.success(request, f"تمت إضافة {added} مرفق(ات).")
                if len(uploaded_files) > remaining_slots:
                    messages.warning(
                        request,
                        "تم تجاوز الحد الأقصى للمرفقات (2). تم رفع جزء فقط من الملفات."
                    )

            # Redirect by save_mode.
            if save_mode == 'print_rx':
                return redirect('print_prescription', visit_id=visit.id)
            return redirect('patient_detail', id=visit.patient.id)

    else:
        form = DoctorVisitForm(
            instance=visit,
            specialty=clinic.specialty, exclude_nurse=True,
        )

    # Dental chart (v2 — 3D, mode-driven). For dentistry clinics we also seed
    # the per-visit plan snapshot so the end-of-visit summary widget shows the
    # correct "planned for today" list.
    dental_v2_data = None
    dental_v2_choices = None
    if clinic.specialty == 'dentistry':
        _ensure_visit_plan_snapshot(visit)
        dental_v2_data = _dental_chart_context(visit.patient, visit)
        dental_v2_choices = {
            'conditions': DENTAL_CONDITION_CHOICES,
            'surfaces':   DENTAL_SURFACE_CHOICES,
            'procedures': DENTAL_PROCEDURE_CHOICES,
            'priorities': TreatmentPlan.PRIORITY_CHOICES,
        }

    vitals_specs = build_field_specs(get_nursing_fields(clinic.specialty))
    # Dentistry uses a stripped-down medical section: the dental chart is the
    # diagnosis & treatment surface, so the dentist only needs notes,
    # prescription, attachments, and next appointment. Everything else
    # (history_of_present_illness, clinical_examination, diagnosis,
    # treatment_plan, patient_instructions, free-text prescription notes) is
    # hidden for the dentistry specialty.
    if clinic.specialty == 'dentistry':
        medical_specs = build_field_specs(['doctor_notes', 'prescription_items'])
    else:
        medical_specs = build_field_specs(
            ['history_of_present_illness', 'clinical_examination']
            + get_specialty_medical_fields(clinic.specialty)
            + COMMON_MEDICAL_FIELDS
        )

    return render(request, 'patients/doctor_complete_visit.html', {
        'form': form,
        'visit': visit,
        # The dental chart partial uses {{ patient.id }} directly, so the
        # patient must be in the template context too.
        'patient': visit.patient,
        'attachment_form': attachment_form,
        'clinic': clinic,
        'specialty': clinic.specialty,
        'quick_picks': get_quick_picks(clinic.specialty),
        'vitals_specs': vitals_specs,
        'medical_specs': medical_specs,
        # Dental chart context (mode-driven SVG chart).
        'dental_v2_data': dental_v2_data,
        'dental_v2_choices': dental_v2_choices,
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
            elif last_visit.status == 'consultation_pending':
                # "Save with consultation" — half-completed visit waiting on
                # specialist / lab / imaging input. Exposed as its own filter
                # chip on the patient list so reception can find them fast.
                visit_status = 'استشارة قيد الانتظار'
                card_class = 'patient-consultation'
                status_key = 'consultation'
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
        # Show fully-completed visits AND consultation-pending visits in the
        # same timeline. The template paints a different header on
        # consultation_pending rows so the doctor can spot them at a glance.
        visits_query = Visit.objects.filter(
            patient=patient,
            status__in=['doctor_completed', 'consultation_pending']
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

    # ── Upcoming bookings (FROM NOW, looking forward) ─────────────────
    # Two sources merged into one chronological list so the section shows
    # BOTH booked appointments and Visit follow-up dates:
    #   1. Appointment rows with status='scheduled' and scheduled_at in the
    #      future (the modern booking flow via "احجز موعد").
    #   2. Visit rows with follow_up_date in the future (legacy follow-ups
    #      saved on the visit itself).
    # Each entry is normalized to a dict so the template doesn't have to
    # branch on type. `cancel_url` differs per kind: appointments go through
    # `cancel_appointment`; follow-ups through `clear_appointment` (which
    # just nulls the field).
    from django.utils import timezone as _tz
    now = _tz.now()
    upcoming_bookings = []
    for a in patient.appointments.filter(scheduled_at__gte=now, status='scheduled').order_by('scheduled_at'):
        upcoming_bookings.append({
            'kind':        'appointment',
            'time':        a.scheduled_at,
            'type_label':  a.get_appt_type_display(),
            'notes':       a.notes,
            'cancel_url':  reverse('cancel_appointment', args=[a.id]),
            'cancel_msg':  'إلغاء هذا الموعد؟',
        })
    for v in Visit.objects.filter(patient=patient, follow_up_date__gte=now).order_by('follow_up_date'):
        upcoming_bookings.append({
            'kind':        'follow_up',
            'time':        v.follow_up_date,
            'type_label':  'مراجعة',
            'notes':       '',
            'cancel_url':  reverse('clear_appointment', args=[v.id]),
            'cancel_msg':  'إزالة موعد المراجعة؟',
        })
    upcoming_bookings.sort(key=lambda b: b['time'])

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
        'upcoming_bookings': upcoming_bookings,
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
    """Delete a visit. Permissions:
      - Doctors can delete completed visits (doctor_completed).
      - Nurses can delete their own nurse_draft visits (before the doctor
        sees them) so they can fix a mis-created entry quickly."""
    profile = UserProfile.objects.get(user=request.user)
    visit = get_object_or_404(Visit, id=id)
    if visit.clinic != profile.clinic:
        return redirect('patient_list')

    user_is_doctor = is_doctor(request.user)
    user_is_nurse = is_nurse(request.user)

    if visit.status == 'doctor_completed':
        if not user_is_doctor:
            messages.error(request, "حذف الزيارات المكتملة متاح للطبيب فقط.")
            return redirect('patient_detail', id=visit.patient.id)
    elif visit.status == 'nurse_draft':
        if not (user_is_nurse or user_is_doctor):
            return redirect('patient_list')
    else:
        messages.error(request, "لا يمكن حذف هذه الزيارة في حالتها الحالية.")
        return redirect('patient_detail', id=visit.patient.id)

    if request.method == 'POST':
        patient_id = visit.patient.id
        visit.delete()
        messages.success(request, "تم حذف الزيارة بنجاح")
        if user_is_nurse and not user_is_doctor:
            return redirect('waiting_list')
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

    # Allow editing visits that are either fully completed OR saved as a
    # consultation (half-completed, awaiting referral). Nurse drafts still
    # go through the doctor_complete_visit flow.
    if visit.status not in ('doctor_completed', 'consultation_pending'):
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
            # Save modes (mirror of doctor_complete_visit):
            #   ''             → status = doctor_completed (normal save)
            #   'consultation' → status = consultation_pending (still half-done)
            # The doctor can edit a consultation_pending visit and SAVE normally
            # to promote it to doctor_completed. Conversely a completed visit
            # can be flipped back to consultation_pending via "حفظ كاستشارة".
            save_mode = (request.POST.get('save_mode') or '').strip()
            visit = form.save(commit=False)
            if save_mode == 'consultation':
                visit.status = 'consultation_pending'
            else:
                visit.status = 'doctor_completed'
            visit.save()

            if save_mode == 'consultation':
                messages.success(request, "تم حفظ التعديلات كاستشارة قيد الانتظار.")
            else:
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

    # Dental chart (v2 — 3D, mode-driven). On edit we just show what's there;
    # the visit is already completed so plan snapshot would already exist.
    dental_v2_data = None
    dental_v2_choices = None
    if clinic.specialty == 'dentistry':
        dental_v2_data = _dental_chart_context(visit.patient, visit)
        dental_v2_choices = {
            'conditions': DENTAL_CONDITION_CHOICES,
            'surfaces':   DENTAL_SURFACE_CHOICES,
            'procedures': DENTAL_PROCEDURE_CHOICES,
            'priorities': TreatmentPlan.PRIORITY_CHOICES,
        }

    vitals_specs = build_field_specs(get_nursing_fields(clinic.specialty))
    # Dentistry edits use the same minimal field set as doctor_complete_visit
    # (chart + notes + prescription items + appointment + attachments). All
    # other medical fields are hidden so they don't reappear when editing.
    if clinic.specialty == 'dentistry':
        medical_specs = build_field_specs(['doctor_notes', 'prescription_items'])
    else:
        medical_specs = build_field_specs(
            ['history_of_present_illness', 'clinical_examination']
            + get_specialty_medical_fields(clinic.specialty)
            + COMMON_MEDICAL_FIELDS
        )

    return render(request, 'patients/edit_visit.html', {
        'form': form,
        'visit': visit,
        # Needed by _dental_chart_3d.html which references {{ patient.id }}.
        'patient': visit.patient,
        'clinic': clinic,
        'attachment_form': attachment_form,
        'specialty': clinic.specialty,
        'quick_picks': get_quick_picks(clinic.specialty),
        'vitals_specs': vitals_specs,
        'medical_specs': medical_specs,
        'dental_v2_data': dental_v2_data,
        'dental_v2_choices': dental_v2_choices,
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
# Unified booking handlers — used by the dashboard "حجوزات اليوم" buttons.
# `kind` is either 'visit' (Visit.follow_up_date — legacy follow-up booking)
# or 'appointment' (Appointment row — modern booking flow via "احجز موعد").
# clear_booking → just removes from today's list.
# enter_booking → removes from today's list AND opens a fresh nurse_draft
#                 for the patient (the "ادخال" button).
# -----------------------------------------------------------------------------
def _resolve_booking_or_redirect(request, kind, item_id):
    """Return (patient, cleanup_callable) for the given booking, or None on
    permission/lookup failure (in which case the caller should redirect to
    dashboard). Raises on bad `kind`."""
    profile = UserProfile.objects.get(user=request.user)
    if kind == 'visit':
        visit = get_object_or_404(Visit, id=item_id, patient__clinic=profile.clinic)
        def _cleanup():
            visit.follow_up_date = None
            visit.save(update_fields=['follow_up_date', 'updated_at'])
        return visit.patient, _cleanup
    elif kind == 'appointment':
        appt = get_object_or_404(Appointment, id=item_id, clinic=profile.clinic)
        def _cleanup():
            appt.status = 'done'
            appt.save(update_fields=['status', 'updated_at'])
        return appt.patient, _cleanup
    return None, None


@login_required(login_url='login')
@require_POST
def clear_booking(request, kind, item_id):
    """Remove a booking (Visit follow-up OR Appointment) from today's list.
    Wired to the "لم يحضر" (didn't attend) button — clears the booking
    without creating any visit."""
    if not (is_doctor(request.user) or is_nurse(request.user)):
        return redirect('dashboard')
    patient, cleanup = _resolve_booking_or_redirect(request, kind, item_id)
    if patient is None:
        return redirect('dashboard')
    cleanup()
    messages.success(request, "تمت إزالة الموعد من قائمة اليوم (المريض لم يحضر).")
    return redirect('dashboard')


@login_required(login_url='login')
@require_POST
def enter_booking(request, kind, item_id):
    """Mark booking done AND open a new nurse-draft for the patient.
    Wired to the "ادخال" button on the dashboard. After clearing the booking
    we redirect to nurse_create_visit, which will either show the form or
    bounce back to patient_detail if there's already a pending visit."""
    if not (is_doctor(request.user) or is_nurse(request.user)):
        return redirect('dashboard')
    patient, cleanup = _resolve_booking_or_redirect(request, kind, item_id)
    if patient is None:
        return redirect('dashboard')
    cleanup()
    messages.success(request, "تم إدخال المريض — يمكن الآن تسجيل البيانات التمريضية.")
    return redirect('nurse_create_visit', patient_id=patient.id)


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
    lines.append(f"المريض: {p.name} | العمر: {p.age_years or p.age or '—'} | الجنس: {p.get_gender_display()}")
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

# -----------------------------------------------------------------------------
# Appointment booking (doctor + nurse) + weekly calendar
# -----------------------------------------------------------------------------
@login_required(login_url='login')
def book_appointment_picker(request):
    """Dedicated patient picker for the "حجز موعد" dashboard card.

    Renders a list-view of every patient in the clinic with a client-side
    filter input on top. Clicking a row goes DIRECTLY to book_appointment
    (NOT patient_detail) so the doctor/nurse can pick a patient and book
    in two clicks. Distinct from the navbar's global search-as-you-type
    (which always opens patient_detail).
    """
    if not (is_doctor(request.user) or is_nurse(request.user)):
        return redirect('dashboard')
    profile = UserProfile.objects.get(user=request.user)
    patients = Patient.objects.filter(clinic=profile.clinic).order_by('name')
    return render(request, 'patients/book_appointment_picker.html', {
        'patients': patients,
    })


@login_required(login_url='login')
def book_appointment(request, patient_id):
    """Doctors AND nurses can book an appointment for a patient. Reached from
    the patient_detail page (the "احجز موعد" button) and from the dashboard
    "احجز موعد" card (which lands on a patient picker page first — for now
    we route directly to the patient list with an `?action=book` flag handled
    on the patient_list template)."""
    if not (is_doctor(request.user) or is_nurse(request.user)):
        return redirect('dashboard')

    profile = UserProfile.objects.get(user=request.user)
    patient = get_object_or_404(Patient, id=patient_id, clinic=profile.clinic)

    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appt = form.save(commit=False)
            appt.clinic = profile.clinic
            appt.patient = patient
            appt.created_by = request.user
            appt.save()
            messages.success(request, "تم حجز الموعد بنجاح.")
            return redirect('patient_detail', id=patient.id)
    else:
        form = AppointmentForm()

    return render(request, 'patients/book_appointment.html', {
        'form': form,
        'patient': patient,
    })


@login_required(login_url='login')
def calendar_view(request):
    """Weekly calendar of scheduled appointments. Navigation via `?week=YYYY-MM-DD`
    where the value is the Saturday at the start of the desired week (Arabic
    week convention). Defaults to current week."""
    from datetime import timedelta as _td, datetime as _dt
    if not request.user.is_authenticated:
        return redirect('login')

    profile = UserProfile.objects.get(user=request.user)
    today = date.today()

    # Compute "week start" — we use Saturday as the start of the week to
    # match Arabic/Levantine convention. Python's weekday(): Mon=0..Sun=6,
    # so Sat=5. Offset from today back to nearest Saturday.
    raw_week = (request.GET.get('week') or '').strip()
    if raw_week:
        try:
            start = _dt.strptime(raw_week, '%Y-%m-%d').date()
        except ValueError:
            start = today - _td(days=(today.weekday() + 2) % 7)
    else:
        start = today - _td(days=(today.weekday() + 2) % 7)

    days = []
    for offset in range(7):
        d = start + _td(days=offset)
        # 1) Real Appointment rows (modern booking flow).
        appts = Appointment.objects.filter(
            clinic=profile.clinic,
            scheduled_at__date=d,
            status='scheduled',
        ).order_by('scheduled_at')
        # 2) Visit follow-ups — older, Visit-tied bookings shown as "مراجعة".
        followups = Visit.objects.filter(
            patient__clinic=profile.clinic,
            follow_up_date__date=d,
        ).order_by('follow_up_date')

        # Normalize both into a single shape the template can render
        # without branching:
        #   { kind, time, patient, type_label, cancel_url, cancel_confirm }
        items = []
        for a in appts:
            items.append({
                'kind': 'appointment',
                'time': a.scheduled_at,
                'patient': a.patient,
                'type_label': a.get_appt_type_display(),
                'cancel_url': reverse('cancel_appointment', args=[a.id]),
                'cancel_confirm': 'إلغاء هذا الموعد؟',
            })
        for v in followups:
            items.append({
                'kind': 'follow_up',
                'time': v.follow_up_date,
                'patient': v.patient,
                'type_label': 'مراجعة',
                # Reusing the legacy clear endpoint — it just nulls follow_up_date.
                'cancel_url': reverse('clear_appointment', args=[v.id]),
                'cancel_confirm': 'إزالة المراجعة من التقويم؟',
            })
        items.sort(key=lambda it: it['time'])

        days.append({
            'date': d,
            'is_today': d == today,
            'appointments': items,
        })

    return render(request, 'patients/calendar.html', {
        'days': days,
        'week_start': start,
        'prev_week': (start - _td(days=7)).strftime('%Y-%m-%d'),
        'next_week': (start + _td(days=7)).strftime('%Y-%m-%d'),
        'today_iso': today.strftime('%Y-%m-%d'),
    })


@login_required(login_url='login')
@require_POST
def cancel_appointment(request, appointment_id):
    """Mark an appointment as cancelled. Reachable from the calendar view."""
    if not (is_doctor(request.user) or is_nurse(request.user)):
        return redirect('dashboard')
    profile = UserProfile.objects.get(user=request.user)
    appt = get_object_or_404(Appointment, id=appointment_id, clinic=profile.clinic)
    appt.status = 'cancelled'
    appt.save(update_fields=['status', 'updated_at'])
    messages.success(request, "تم إلغاء الموعد.")
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('calendar')


# -----------------------------------------------------------------------------
# A5 prescription print
# -----------------------------------------------------------------------------
@login_required(login_url='login')
def print_prescription(request, visit_id):
    """Render an A5-formatted prescription for a single visit. Designed to
    auto-open the browser print dialog. Only available to doctors inside the
    same clinic."""
    if not is_doctor(request.user):
        return redirect('dashboard')

    profile = UserProfile.objects.get(user=request.user)
    visit = get_object_or_404(Visit, id=visit_id, clinic=profile.clinic)

    # Decode structured prescription rows if present.
    items = []
    raw_items = (visit.prescription_items or '').strip()
    if raw_items:
        try:
            decoded = _json_specs.loads(raw_items)
            if isinstance(decoded, list):
                items = [r for r in decoded if isinstance(r, dict) and r.get('name')]
        except Exception:
            items = []

    # Doctor display name + specialty text-form (clinic.specialty_type takes
    # precedence over the internal enum so the doctor sees the wording the
    # admin set on the account page).
    clinic = visit.clinic
    specialty_label = (clinic.specialty_type or '').strip() or clinic.get_specialty_display()
    doctor_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username

    return render(request, 'patients/print_prescription.html', {
        'visit': visit,
        'patient': visit.patient,
        'clinic': clinic,
        'items': items,
        'free_text': (visit.prescription or '').strip(),
        'specialty_label': specialty_label,
        'doctor_name': doctor_name,
    })


# end of views.py

# =============================================================================
# Dental chart v2 -- examination / plan / procedures
# =============================================================================
#
# Wiring overview
# ---------------
# The 3D chart template (`_dental_chart_3d.html`) gets all current data from
# `_dental_chart_context(patient, visit)` and posts back via these AJAX
# endpoints. There are deliberately no Django forms for the chart -- each
# endpoint takes a small JSON body and returns either `{"ok": True, ...}` on
# success or `{"ok": False, "error": "..."}` on failure. Keeps the JS layer
# thin and easy to debug from the network panel.
#
# All endpoints validate:
#   - the patient/visit belongs to the requesting user's clinic
#   - the user is a doctor (the dentist is always a doctor here)
#   - the tooth/surface/procedure code is in the allow-list shared with the
#     models module
# -----------------------------------------------------------------------------

_VALID_TEETH       = {t for t, _lbl in DENTAL_TOOTH_CHOICES}
_VALID_SURFACES    = {s for s, _lbl in DENTAL_SURFACE_CHOICES}
_VALID_CONDITIONS  = {c for c, _lbl in DENTAL_CONDITION_CHOICES}
_VALID_PROCEDURES  = {p for p, _lbl in DENTAL_PROCEDURE_CHOICES}
_VALID_PRIORITIES  = {p for p, _lbl in TreatmentPlan.PRIORITY_CHOICES}


def _read_json(request):
    """Parse JSON body. Returns (payload, error_response_or_None)."""
    try:
        return _json.loads(request.body.decode('utf-8') or '{}'), None
    except ValueError:
        return None, JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)


def _ensure_dental_access(request, patient_id=None, visit_id=None):
    """Confirm the user is a doctor in the patient/visit's clinic.

    Returns (patient, visit, error_response). Either patient or visit is
    resolved depending on which id was supplied; the other is derived. If
    access is denied or the user isn't a doctor, the error_response is
    populated and the caller should return it.
    """
    if not is_doctor(request.user):
        return None, None, JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)
    profile = UserProfile.objects.get(user=request.user)
    visit = None
    if visit_id is not None:
        visit = get_object_or_404(Visit, id=visit_id, clinic=profile.clinic)
        patient = visit.patient
    elif patient_id is not None:
        patient = get_object_or_404(Patient, id=patient_id, clinic=profile.clinic)
    else:
        return None, None, JsonResponse({'ok': False, 'error': 'no_id'}, status=400)
    return patient, visit, None


def _serialize_status(s):
    return {
        'id': s.id,
        'tooth': s.tooth_number,
        'surface': s.surface,
        'condition': s.condition,
        'condition_label': dict(DENTAL_CONDITION_CHOICES).get(s.condition, s.condition),
        'note': s.note,
        'visit_id': s.last_updated_visit_id,
        'updated_at': s.updated_at.isoformat() if s.updated_at else None,
    }


def _serialize_step(step):
    return {
        'id': step.id,
        'plan_id': step.plan_id,
        'tooth': step.tooth_number,
        'surface': step.surface,
        'procedure': step.procedure,
        'procedure_label': dict(DENTAL_PROCEDURE_CHOICES).get(step.procedure, step.procedure),
        'priority': step.priority,
        'priority_label': dict(TreatmentPlan.PRIORITY_CHOICES).get(step.priority, step.priority),
        'status': step.status,
        'status_label': dict(PlanStep.STATUS_CHOICES).get(step.status, step.status),
        'notes': step.notes,
        'canals': step.canals,
        'sequence': step.sequence,
        'plan_status': step.plan.status,
    }


def _serialize_procedure(p):
    return {
        'id': p.id,
        'visit_id': p.visit_id,
        'tooth': p.tooth_number,
        'surface': p.surface,
        'surfaces_csv': p.surfaces_csv,
        'all_surfaces': p.all_surfaces,
        'procedure': p.procedure,
        'procedure_label': dict(DENTAL_PROCEDURE_CHOICES).get(p.procedure, p.procedure),
        'material': p.material,
        'canals': p.canals,
        'notes': p.notes,
        'plan_step_id': p.plan_step_id,
        'created_at': p.created_at.isoformat() if p.created_at else None,
    }


def _dental_chart_context(patient, visit=None):
    """Bundle everything the chart template needs into one dict.

    Each table lookup is wrapped in try/except so that if the user hasn't
    applied the new dental migrations yet, the page still renders an empty
    chart instead of a 500. The error is logged but suppressed.
    """
    from django.db import DatabaseError
    statuses = []
    plan_steps = []
    procedures = []
    history = []
    snapshot_ids = []
    try:
        statuses = [_serialize_status(s) for s in patient.tooth_statuses.all()]
    except DatabaseError as e:
        logging.getLogger(__name__).warning('dental: tooth_statuses unavailable (run migrations?): %s', e)
    try:
        plan_qs = TreatmentPlan.objects.filter(patient=patient).exclude(status='cancelled')
        steps = PlanStep.objects.filter(plan__in=plan_qs).select_related('plan').order_by('plan_id', 'sequence', 'created_at')
        plan_steps = [_serialize_step(st) for st in steps]
    except DatabaseError as e:
        logging.getLogger(__name__).warning('dental: plan steps unavailable (run migrations?): %s', e)
    if visit is not None:
        try:
            for p in visit.dental_procedures.all().order_by('-created_at'):
                procedures.append(_serialize_procedure(p))
            prev = (
                VisitProcedure.objects
                .filter(visit__patient=patient)
                .exclude(visit_id=visit.id)
                .select_related('visit')
                .order_by('-created_at')[:200]
            )
            for p in prev:
                row = _serialize_procedure(p)
                row['visit_date'] = p.visit.created_at.isoformat() if p.visit.created_at else None
                history.append(row)
            snapshot_ids = list(visit.plan_snapshots.values_list('plan_step_id', flat=True))
        except DatabaseError as e:
            logging.getLogger(__name__).warning('dental: procedures unavailable (run migrations?): %s', e)
    return {
        'statuses': statuses,
        'plan_steps': plan_steps,
        'procedures': procedures,
        'history': history,
        'snapshot': snapshot_ids,
    }


def _ensure_visit_plan_snapshot(visit):
    """First time the dental chart is opened for a visit, freeze the list of
    pending plan steps so the end-of-visit summary can compare 'planned for
    today' vs 'done today' accurately even if new plan steps are created
    mid-visit. Idempotent. Swallows DatabaseError so the page still renders
    when the dental migrations haven't been applied yet."""
    from django.db import DatabaseError
    try:
        if visit.plan_snapshots.exists():
            return
        pending_step_ids = (
            PlanStep.objects
            .filter(plan__patient=visit.patient, status='pending')
            .exclude(plan__status='cancelled')
            .values_list('id', flat=True)
        )
        VisitPlanSnapshot.objects.bulk_create(
            [VisitPlanSnapshot(visit=visit, plan_step_id=pid) for pid in pending_step_ids]
        )
    except DatabaseError as e:
        logging.getLogger(__name__).warning('dental: snapshot skipped (run migrations?): %s', e)


# -----------------------------------------------------------------------------
# Examination mode endpoint
# -----------------------------------------------------------------------------
@login_required(login_url='login')
@require_POST
def dental_update_status(request, patient_id):
    """Create / update / clear one tooth surface examination finding."""
    patient, _v, err = _ensure_dental_access(request, patient_id=patient_id)
    if err:
        return err
    payload, perr = _read_json(request)
    if perr:
        return perr

    tooth = str(payload.get('tooth', '')).strip()
    surface = str(payload.get('surface', 'whole')).strip() or 'whole'
    condition = str(payload.get('condition', '')).strip()
    note = str(payload.get('note', '') or '')[:200]
    visit_id = payload.get('visit_id')

    if tooth not in _VALID_TEETH:
        return JsonResponse({'ok': False, 'error': 'bad_tooth'}, status=400)
    if surface not in _VALID_SURFACES:
        return JsonResponse({'ok': False, 'error': 'bad_surface'}, status=400)

    # Empty condition -> clear that surface (delete the row).
    if condition == '':
        ToothStatus.objects.filter(patient=patient, tooth_number=tooth, surface=surface).delete()
        return JsonResponse({'ok': True, 'cleared': True})

    if condition not in _VALID_CONDITIONS:
        return JsonResponse({'ok': False, 'error': 'bad_condition'}, status=400)

    visit = None
    if visit_id:
        profile = UserProfile.objects.get(user=request.user)
        visit = Visit.objects.filter(id=visit_id, clinic=profile.clinic, patient=patient).first()

    obj, _created = ToothStatus.objects.update_or_create(
        patient=patient, tooth_number=tooth, surface=surface,
        defaults={'condition': condition, 'note': note, 'last_updated_visit': visit},
    )
    return JsonResponse({'ok': True, 'status': _serialize_status(obj)})


# -----------------------------------------------------------------------------
# Plan mode endpoints
# -----------------------------------------------------------------------------
@login_required(login_url='login')
@require_POST
def dental_create_plan_step(request, patient_id):
    """Add a plan step. If `plan_id` is supplied, append to that plan;
    otherwise create a single-step plan and use it."""
    patient, _v, err = _ensure_dental_access(request, patient_id=patient_id)
    if err:
        return err
    payload, perr = _read_json(request)
    if perr:
        return perr

    tooth = str(payload.get('tooth', '')).strip()
    surface = str(payload.get('surface', 'whole')).strip() or 'whole'
    procedure = str(payload.get('procedure', '')).strip()
    priority = str(payload.get('priority', 'necessary')).strip() or 'necessary'
    notes = str(payload.get('notes', '') or '')[:300]
    canals = str(payload.get('canals', '') or '')[:120]
    plan_id = payload.get('plan_id')

    if tooth not in _VALID_TEETH:
        return JsonResponse({'ok': False, 'error': 'bad_tooth'}, status=400)
    if surface not in _VALID_SURFACES:
        return JsonResponse({'ok': False, 'error': 'bad_surface'}, status=400)
    if procedure not in _VALID_PROCEDURES:
        return JsonResponse({'ok': False, 'error': 'bad_procedure'}, status=400)
    if priority not in _VALID_PRIORITIES:
        priority = 'necessary'

    plan = None
    if plan_id:
        plan = TreatmentPlan.objects.filter(id=plan_id, patient=patient).first()
    if plan is None:
        plan = TreatmentPlan.objects.create(
            patient=patient,
            priority=priority,
            created_by=request.user,
        )

    last_seq = plan.steps.order_by('-sequence').values_list('sequence', flat=True).first() or 0

    step = PlanStep.objects.create(
        plan=plan,
        tooth_number=tooth,
        surface=surface,
        procedure=procedure,
        priority=priority,
        notes=notes,
        canals=canals,
        sequence=last_seq + 1,
    )
    plan.recalc_status()
    return JsonResponse({'ok': True, 'step': _serialize_step(step)})


@login_required(login_url='login')
@require_POST
def dental_update_plan_step(request, patient_id, step_id):
    """Edit an existing plan step."""
    patient, _v, err = _ensure_dental_access(request, patient_id=patient_id)
    if err:
        return err
    step = get_object_or_404(PlanStep, id=step_id, plan__patient=patient)
    payload, perr = _read_json(request)
    if perr:
        return perr

    if 'procedure' in payload:
        proc = str(payload['procedure']).strip()
        if proc not in _VALID_PROCEDURES:
            return JsonResponse({'ok': False, 'error': 'bad_procedure'}, status=400)
        step.procedure = proc
    if 'priority' in payload:
        pr = str(payload['priority']).strip()
        if pr in _VALID_PRIORITIES:
            step.priority = pr
    if 'notes' in payload:
        step.notes = str(payload['notes'] or '')[:300]
    if 'canals' in payload:
        step.canals = str(payload['canals'] or '')[:120]
    if 'status' in payload and payload['status'] in {'pending', 'done'}:
        step.status = payload['status']
    step.save()
    step.plan.recalc_status()
    return JsonResponse({'ok': True, 'step': _serialize_step(step)})


@login_required(login_url='login')
@require_POST
def dental_delete_plan_step(request, patient_id, step_id):
    patient, _v, err = _ensure_dental_access(request, patient_id=patient_id)
    if err:
        return err
    step = get_object_or_404(PlanStep, id=step_id, plan__patient=patient)
    plan = step.plan
    step.delete()
    plan.recalc_status()
    # If we just emptied a plan, mark it cancelled so it stops showing up.
    if not plan.steps.exists():
        plan.status = 'cancelled'
        plan.save(update_fields=['status', 'updated_at'])
    return JsonResponse({'ok': True, 'cleared': True})


# -----------------------------------------------------------------------------
# Procedures mode endpoints
# -----------------------------------------------------------------------------
@login_required(login_url='login')
@require_POST
def dental_create_procedure(request, visit_id):
    """Record a completed procedure on the current visit. If `plan_step_id`
    is set, the corresponding plan step is auto-flipped to `done` and the
    parent plan's status is recomputed."""
    patient, visit, err = _ensure_dental_access(request, visit_id=visit_id)
    if err:
        return err
    payload, perr = _read_json(request)
    if perr:
        return perr

    tooth = str(payload.get('tooth', '')).strip()
    surface = str(payload.get('surface', 'whole')).strip() or 'whole'
    procedure = str(payload.get('procedure', '')).strip()
    material = str(payload.get('material', '') or '')[:80]
    canals = str(payload.get('canals', '') or '')[:120]
    notes = str(payload.get('notes', '') or '')[:400]
    plan_step_id = payload.get('plan_step_id')
    extras = payload.get('extra_surfaces') or []

    if tooth not in _VALID_TEETH:
        return JsonResponse({'ok': False, 'error': 'bad_tooth'}, status=400)
    if surface not in _VALID_SURFACES:
        return JsonResponse({'ok': False, 'error': 'bad_surface'}, status=400)
    if procedure not in _VALID_PROCEDURES:
        return JsonResponse({'ok': False, 'error': 'bad_procedure'}, status=400)

    if isinstance(extras, list):
        extras_clean = [str(s).strip() for s in extras if str(s).strip() in _VALID_SURFACES]
    else:
        extras_clean = []
    surfaces_csv = ','.join(extras_clean)

    step = None
    if plan_step_id:
        step = PlanStep.objects.filter(id=plan_step_id, plan__patient=patient).first()

    proc = VisitProcedure.objects.create(
        visit=visit,
        plan_step=step,
        tooth_number=tooth,
        surface=surface,
        surfaces_csv=surfaces_csv,
        procedure=procedure,
        material=material,
        canals=canals,
        notes=notes,
        performed_by=request.user,
    )
    if step is not None:
        step.status = 'done'
        step.save(update_fields=['status', 'updated_at'])
        step.plan.recalc_status()

    return JsonResponse({'ok': True, 'procedure': _serialize_procedure(proc)})


@login_required(login_url='login')
@require_POST
def dental_delete_procedure(request, visit_id, procedure_id):
    """Remove a completed procedure. If it was linked to a plan step we
    revert the step back to `pending` (the dentist may have miss-clicked)."""
    patient, visit, err = _ensure_dental_access(request, visit_id=visit_id)
    if err:
        return err
    proc = get_object_or_404(VisitProcedure, id=procedure_id, visit=visit)
    step = proc.plan_step
    proc.delete()
    if step is not None:
        if not step.procedures.exists():
            step.status = 'pending'
            step.save(update_fields=['status', 'updated_at'])
            step.plan.recalc_status()
    return JsonResponse({'ok': True, 'cleared': True})


# -----------------------------------------------------------------------------
# Standalone dental chart page (entry point from patient_detail)
# -----------------------------------------------------------------------------
def _resolve_active_visit(patient, requested_visit_id=None):
    """Find the visit to anchor the chart to. Priority:
       1. explicit ?visit=<id> in the query string
       2. patient's most recent nurse_draft / consultation_pending visit
       3. patient's most recent visit overall
       4. None -- chart loads with Procedures mode disabled
    """
    if requested_visit_id:
        v = patient.visits.filter(id=requested_visit_id).first()
        if v:
            return v
    open_v = (
        patient.visits
        .filter(status__in=['nurse_draft', 'consultation_pending'])
        .order_by('-created_at')
        .first()
    )
    if open_v:
        return open_v
    return patient.visits.order_by('-created_at').first()

@login_required(login_url='login')

@login_required(login_url='login')
def dental_chart_page(request, patient_id):
    """Standalone full-page dental chart for a patient. Visit context is
    optional -- if no visit is open, Procedures mode is disabled (the dentist
    can still examine and plan)."""
    if not is_doctor(request.user):
        return redirect('patient_list')
    profile = UserProfile.objects.get(user=request.user)
    patient = get_object_or_404(Patient, id=patient_id, clinic=profile.clinic)

    visit = _resolve_active_visit(patient, request.GET.get('visit'))
    if visit is not None:
        _ensure_visit_plan_snapshot(visit)

    ctx_data = _dental_chart_context(patient, visit)

    return render(request, 'patients/dental_chart_page.html', {
        'patient': patient,
        'visit': visit,
        'dental_v2_data': ctx_data,
        'dental_v2_choices': {
            'conditions': DENTAL_CONDITION_CHOICES,
            'surfaces':   DENTAL_SURFACE_CHOICES,
            'procedures': DENTAL_PROCEDURE_CHOICES,
            'priorities': TreatmentPlan.PRIORITY_CHOICES,
        },
    })


# end of views.py
