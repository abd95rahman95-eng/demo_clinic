from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from .models import Patient, Visit, UserProfile
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from .forms import PatientForm, NurseVisitForm, DoctorVisitForm
from django.contrib.auth.models import User
from datetime import date


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
        'is_doctor': is_doctor(request.user),
        'is_nurse': is_nurse(request.user),
    })

@login_required(login_url='login')
def nurse_create_visit(request, patient_id):
    if not is_nurse(request.user):
        return redirect('patient_list')

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

    return render(request, 'patients/nurse_create_visit.html', {
        'form': form,
        'patient': patient,
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
    visit = get_object_or_404(Visit, id=visit_id)

    if visit.clinic != profile.clinic:
        return redirect('patient_list')

    if visit.assigned_doctor != request.user:
        return redirect('doctor_pending_visits')

    if request.method == 'POST':
        form = DoctorVisitForm(request.POST, instance=visit)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.status = 'doctor_completed'
            visit.save()

            messages.success(request, "تم إكمال الزيارة بنجاح")
            return redirect('patient_detail', id=visit.patient.id)
    else:
        form = DoctorVisitForm(instance=visit)

    return render(request, 'patients/doctor_complete_visit.html', {
        'form': form,
        'visit': visit,
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

    paginator = Paginator(patients_with_status_all, 4)
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
    if is_doctor(request.user):
        visits = Visit.objects.filter(
            patient=patient,
            status='doctor_completed'
        ).order_by('-created_at')

    return render(request, 'patients/patient_detail.html', {
        'patient': patient,
        'pending_visit': pending_visit,
        'visits': visits,
        'is_doctor': is_doctor(request.user),
        'is_nurse': is_nurse(request.user),
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

    form = DoctorVisitForm(request.POST or None, instance=visit)

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل الزيارة بنجاح")
            return redirect('patient_detail', id=visit.patient.id)

    return render(request, 'patients/edit_visit.html', {
        'form': form,
        'visit': visit,
    })

@login_required(login_url='login')
def nurse_edit_visit(request, id):
    if not is_nurse(request.user):
        return redirect('patient_list')

    profile = UserProfile.objects.get(user=request.user)
    visit = get_object_or_404(Visit, id=id)

    # حماية
    if visit.patient.clinic != profile.clinic:
        return redirect('patient_list')

    # لا يسمح بالتعديل بعد إكمال الطبيب
    if visit.status != 'nurse_draft':
        return redirect('patient_detail', id=visit.patient.id)

    if request.method == 'POST':
        visit.chief_complaint = request.POST['chief_complaint']
        visit.nursing_notes = request.POST['nursing_notes']
        visit.blood_pressure = request.POST['blood_pressure']
        visit.pulse = request.POST['pulse']
        visit.temperature = request.POST['temperature']
        visit.weight = request.POST['weight']
        visit.height = request.POST['height']
        visit.blood_sugar = request.POST['blood_sugar']

        visit.save()

        messages.success(request, "تم تعديل الزيارة التمريضية")
        return redirect('patient_detail', id=visit.patient.id)

    return render(request, 'patients/nurse_edit_visit.html', {
        'visit': visit
    })

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
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