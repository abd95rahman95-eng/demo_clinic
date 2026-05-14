from django import forms
from django.contrib.auth.models import User
from .models import Visit, UserProfile, Patient, VisitAttachment, SignupRequest, Appointment
from .specialty_lists import (
    get_nursing_fields,
    get_specialty_medical_fields,
    ALL_NURSING_VITALS,
    ALL_SPECIALTY_MEDICAL_FIELDS,
)
import datetime as _dt
import re as _re

class PatientForm(forms.ModelForm):
    # ── Birth year / month / day inputs ───────────────────────────────────
    # We expose three separate inputs instead of a single date picker because
    # clinics often know only the patient's birth YEAR and have to guess the
    # rest. Month + day are optional and default to 1/1.
    birth_year = forms.IntegerField(
        label='سنة الميلاد',
        required=False,
        min_value=1900,
        max_value=2100,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'inputmode': 'numeric',
            'placeholder': 'مثال: 1990',
        }),
        help_text='اختياري. إذا تُرك فارغاً يبقى العمر كما هو.',
    )
    birth_month = forms.IntegerField(
        label='شهر الميلاد',
        required=False, min_value=1, max_value=12,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'inputmode': 'numeric', 'placeholder': '1-12'}),
        help_text='اختياري — افتراضياً 1 (كانون الثاني).',
    )
    birth_day = forms.IntegerField(
        label='يوم الميلاد',
        required=False, min_value=1, max_value=31,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'inputmode': 'numeric', 'placeholder': '1-31'}),
        help_text='اختياري — افتراضياً 1.',
    )

    class Meta:
        model = Patient
        # `age` is intentionally NOT in this list anymore — we compute it
        # from birth_date on save. Keeping the field on the model is for
        # backward-compat (existing patients without birth_date).
        fields = ['name', 'phone', 'gender', 'address']
        labels = {
            'name': 'الاسم',
            'phone': 'رقم الهاتف (10 أرقام)',
            'gender': 'الجنس',
            'address': 'العنوان',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                # type=tel surfaces the numeric keypad on mobile while still
                # allowing leading zero (which type=number would strip).
                'type': 'tel',
                'inputmode': 'numeric',
                'pattern': r'[0-9]{10}',
                'maxlength': '10',
                'placeholder': '10 أرقام',
                'title': 'يجب أن يحتوي على 10 أرقام فقط',
                # Strip non-digits as the user types so the field physically
                # cannot contain anything but digits. Paired with the existing
                # server-side `clean_phone` validator for safety.
                'oninput': "this.value=this.value.replace(/\\D+/g,'')",
                'onkeypress': "return /[0-9]/.test(event.key)",
            }),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill the birth-date pickers from the saved value when editing.
        inst = getattr(self, 'instance', None)
        if inst and inst.pk and inst.birth_date:
            self.fields['birth_year'].initial = inst.birth_date.year
            self.fields['birth_month'].initial = inst.birth_date.month
            self.fields['birth_day'].initial = inst.birth_date.day

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        if not phone:
            raise forms.ValidationError("رقم الهاتف مطلوب.")
        if not _re.fullmatch(r'\d{10}', phone):
            raise forms.ValidationError("رقم الهاتف يجب أن يكون 10 أرقام بالضبط.")
        return phone

    def clean_gender(self):
        gender = self.cleaned_data.get('gender')
        if gender not in ['Male', 'Female']:
            raise forms.ValidationError("الجنس يجب أن يكون ذكر أو أنثى.")
        return gender

    def clean(self):
        cleaned = super().clean()
        year = cleaned.get('birth_year')
        month = cleaned.get('birth_month') or 1
        day = cleaned.get('birth_day') or 1
        if year:
            try:
                bdate = _dt.date(int(year), int(month), int(day))
            except ValueError:
                raise forms.ValidationError("تاريخ الميلاد غير صالح — تأكد من الشهر/اليوم.")
            if bdate > _dt.date.today():
                raise forms.ValidationError("تاريخ الميلاد لا يمكن أن يكون في المستقبل.")
            cleaned['_resolved_birth_date'] = bdate
        return cleaned

    def save(self, commit=True):
        patient = super().save(commit=False)
        # If the form provided a year, derive birth_date + computed age.
        resolved = self.cleaned_data.get('_resolved_birth_date')
        if resolved:
            patient.birth_date = resolved
            today = _dt.date.today()
            years = today.year - resolved.year
            if (today.month, today.day) < (resolved.month, resolved.day):
                years -= 1
            patient.age = max(0, years)
        # Else: keep whatever's already on the record. Brand-new patients
        # without a year/age get age=None (column is nullable now).
        if commit:
            patient.save()
        return patient
    
class NurseVisitForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = [
            'visit_type',
            'assigned_doctor',
            'chief_complaint',
            'nursing_notes',
            'blood_pressure',
            'pulse',
            'temperature',
            'weight',
            'height',
            'blood_sugar',
        ]
        labels = {
            'visit_type': 'نوع الزيارة',
            'assigned_doctor': 'الطبيب المسؤول',
            'chief_complaint': 'الشكوى الرئيسية',
            'nursing_notes': 'ملاحظات تمريضية',
            'blood_pressure': 'ضغط الدم',
            'pulse': 'النبض',
            'temperature': 'الحرارة',
            'weight': 'الوزن',
            'height': 'الطول',
            'blood_sugar': 'سكر الدم',
        }
        widgets = {
            'visit_type': forms.Select(attrs={'class': 'form-control'}),
            'assigned_doctor': forms.Select(attrs={'class': 'form-control'}),
            'chief_complaint': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'nursing_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'blood_pressure': forms.TextInput(attrs={'class': 'form-control'}),
            'pulse': forms.TextInput(attrs={'class': 'form-control'}),
            'temperature': forms.TextInput(attrs={'class': 'form-control'}),
            'weight': forms.TextInput(attrs={'class': 'form-control'}),
            'height': forms.TextInput(attrs={'class': 'form-control'}),
            'blood_sugar': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        clinic = kwargs.pop('clinic', None)
        super().__init__(*args, **kwargs)

        if clinic:
            doctors = User.objects.filter(
                groups__name='Doctor',
                userprofile__clinic=clinic
            ).distinct()

            self.fields['assigned_doctor'].queryset = doctors

            if doctors.count() == 1:
                self.fields['assigned_doctor'].initial = doctors.first()
                self.fields['assigned_doctor'].widget = forms.HiddenInput()
            elif doctors.count() == 0:
                self.fields['assigned_doctor'].queryset = User.objects.none()

            # Drop vitals not used by this specialty (e.g. dermatology has no
            # weight/blood_sugar). Driven by SPECIALTY_NURSING_FIELDS.
            allowed_vitals = set(get_nursing_fields(clinic.specialty))
            for f in ALL_NURSING_VITALS:
                if f not in allowed_vitals and f in self.fields:
                    self.fields.pop(f, None)

    def clean_assigned_doctor(self):
        doctor = self.cleaned_data.get('assigned_doctor')
        if not doctor:
            raise forms.ValidationError("لا يوجد طبيب متاح في هذه العيادة.")
        return doctor


# 👈 نموذج الزيارة 

class DoctorVisitForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = [
            # Nurse-entered fields (doctor may correct/complete)
            'visit_type',
            'chief_complaint',
            'nursing_notes',
            'blood_pressure',
            'pulse',
            'temperature',
            'weight',
            'height',
            'blood_sugar',
            # Doctor fields
            'history_of_present_illness',
            'clinical_examination',
            'diagnosis',
            'treatment_plan',
            'prescription',
            'prescription_items',
            'lab_requests',
            'imaging_requests',
            'patient_instructions',
            'follow_up_date',
            'doctor_notes',
            'imaging_results',
            'lab_results',
            # cardiology
            'ecg_results',
            'ejection_fraction',
            'cardiac_history',
            'chest_pain_type',
            'cardiac_medications',
            # orthopedics
            'pain_location',
            'pain_scale',
            'injury_history',
            'range_of_motion',
            'xray_findings',
            # gynecology
            'last_menstrual_period',
            'cycle_regularity',
            'obstetric_history',
            'contraception_method',
            'gestational_age_weeks',
            'abdominal_circumference',
            'fundal_height',
            'fetal_heart_rate',
            'fetal_movement',
            'fetal_position',
            'ultrasound_notes',
            # neurology
            'CT_MRI_findings',
            'neurological_examination',
            # dermatology
            'skin_examination',
            
        ]
        labels = {
            'visit_type': 'نوع الزيارة',
            'chief_complaint': 'الشكوى الرئيسية',
            'nursing_notes': 'ملاحظات تمريضية',
            'blood_pressure': 'ضغط الدم',
            'pulse': 'النبض',
            'temperature': 'الحرارة',
            'weight': 'الوزن',
            'height': 'الطول',
            'blood_sugar': 'سكر الدم',
            'history_of_present_illness': 'القصة المرضية الحالية',
            'clinical_examination': 'الفحص السريري',
            'diagnosis': 'التشخيص',
            'treatment_plan': 'الخطة العلاجية',
            'prescription': 'ملاحظات الوصفة (نص حر — اختياري)',
            'prescription_items': 'وصفة الأدوية',
            'lab_requests': 'طلبات التحاليل',
            'imaging_requests': 'طلبات الصور',
            'patient_instructions': 'تعليمات للمريض',
            'follow_up_date': 'موعد المراجعة القادم',
            'doctor_notes': 'ملاحظات الطبيب',
            'imaging_results': 'نتائج الصور',
            'lab_results': 'نتائج التحاليل',
            # cardiology
            'ecg_results':          'نتائج تخطيط القلب',
            'ejection_fraction':    'كسر القذف',
            'cardiac_history':      'تاريخ أمراض القلب',
            'chest_pain_type':      'نوع ألم الصدر',
            'cardiac_medications':  'أدوية القلب',
            # orthopedics
            'pain_location':        'مكان الألم',
            'pain_scale':           'مقياس الألم (1–10)',
            'injury_history':       'تاريخ الإصابة',
            'range_of_motion':      'مجال الحركة',
            'xray_findings':        'نتائج الأشعة السينية',
            # gynecology
            'last_menstrual_period': 'تاريخ آخر دورة شهرية',
            'cycle_regularity':     'انتظام الدورة',
            'obstetric_history':    'تاريخ الولادة',
            'contraception_method': 'وسيلة منع الحمل',
            'gestational_age_weeks': 'عمر الحمل (أسابيع)',
            'abdominal_circumference': 'محيط البطن',
            'fundal_height':        'ارتفاع قاع الرحم',
            'fetal_heart_rate':     'نبض الجنين',
            'fetal_movement':       'حركة الجنين',
            'fetal_position':       'وضعية الجنين',
            'ultrasound_notes':     'ملاحظات الإيكو',

            # neurology
            'CT_MRI_findings':      'نتائج الأشعة المقطعية والرنين المغناطيسي',
            'neurological_examination': 'الفحص العصبي',
            # dermatology
            'skin_examination':     'فحص الجلد',
        }
        widgets = {
            'visit_type':      forms.Select(attrs={'class': 'form-control'}),
            'chief_complaint': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'nursing_notes':   forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'blood_pressure':  forms.TextInput(attrs={'class': 'form-control'}),
            'pulse':           forms.TextInput(attrs={'class': 'form-control'}),
            'temperature':     forms.TextInput(attrs={'class': 'form-control'}),
            'weight':          forms.TextInput(attrs={'class': 'form-control'}),
            'height':          forms.TextInput(attrs={'class': 'form-control'}),
            'blood_sugar':     forms.TextInput(attrs={'class': 'form-control'}),
            'history_of_present_illness': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'clinical_examination': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'diagnosis': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'treatment_plan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'prescription': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'ملاحظات إضافية على الوصفة (اختياري) — الأدوية تُدخل بالأعلى.'}),
            # Hidden — populated client-side by the structured rows UI on
            # doctor_complete_visit.html (JSON-encoded list of medicine
            # dicts). The template renders the table; this just carries
            # the serialized payload back to the server on submit.
            'prescription_items': forms.HiddenInput(attrs={'data-prescription-items': '1'}),
            'lab_requests': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'imaging_requests': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'patient_instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'follow_up_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'doctor_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'imaging_results': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'lab_results': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            
            # existing widgets stay the same, add new ones:
            'ecg_results':          forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'ejection_fraction':    forms.TextInput(attrs={'class': 'form-control'}),
            'cardiac_history':      forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'chest_pain_type':      forms.TextInput(attrs={'class': 'form-control'}),
            'cardiac_medications':  forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),

            'pain_location':        forms.TextInput(attrs={'class': 'form-control'}),
            'pain_scale':           forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
            'injury_history':       forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'range_of_motion':      forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'xray_findings':        forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),

            'last_menstrual_period': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'cycle_regularity':     forms.TextInput(attrs={'class': 'form-control'}),
            'obstetric_history':    forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'contraception_method': forms.TextInput(attrs={'class': 'form-control'}),
            'gestational_age_weeks': forms.NumberInput(attrs={'class': 'form-control'}),
            'abdominal_circumference': forms.TextInput(attrs={'class': 'form-control'}),
            'fundal_height':        forms.TextInput(attrs={'class': 'form-control'}),
            'fetal_heart_rate':     forms.TextInput(attrs={'class': 'form-control'}),
            'fetal_movement':       forms.TextInput(attrs={'class': 'form-control'}),
            'fetal_position':       forms.TextInput(attrs={'class': 'form-control'}),
            'ultrasound_notes':     forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),

            'CT_MRI_findings':      forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'neurological_examination': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'skin_examination':     forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    # Nurse-side fields. When `exclude_nurse=True` is passed, the form will
    # drop these so the doctor's complete-visit POST can't accidentally
    # overwrite nurse data — the doctor edits nurse data via the dedicated
    # nurse-edit page instead.
    NURSE_FIELDS = (
        'visit_type',
        'chief_complaint', 'nursing_notes',
        'blood_pressure', 'pulse', 'temperature',
        'weight', 'height', 'blood_sugar',
    )

    def __init__(self, *args, **kwargs):
        # Custom kwargs — must pop BEFORE calling super().
        specialty     = kwargs.pop('specialty', None)
        exclude_nurse = kwargs.pop('exclude_nurse', False)

        super().__init__(*args, **kwargs)

        # Allow HTML5 datetime-local input format ("YYYY-MM-DDTHH:MM")
        # in addition to Django's default DateTimeField formats.
        self.fields['follow_up_date'].input_formats = [
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
        ]

        # Drop specialty-specific medical fields that don't belong to this
        # clinic's specialty (e.g. ejection_fraction in a dermatology clinic).
        if specialty is not None:
            allowed = set(get_specialty_medical_fields(specialty))
            for f in ALL_SPECIALTY_MEDICAL_FIELDS:
                if f not in allowed and f in self.fields:
                    self.fields.pop(f, None)

            # Vitals not used by this specialty — drop them too so the doctor
            # doesn't see stale fields if they appear on the form anywhere.
            allowed_vitals = set(get_nursing_fields(specialty))
            for f in ALL_NURSING_VITALS:
                if f not in allowed_vitals and f in self.fields:
                    self.fields.pop(f, None)

        # In the doctor-complete flow, the nurse fields are read-only on the
        # page and edited via nurse_edit_visit. Drop them from this form so
        # the doctor's submit can never blow them away.
        if exclude_nurse:
            for f in self.NURSE_FIELDS:
                self.fields.pop(f, None)


class VisitAttachmentForm(forms.ModelForm):
    class Meta:
        model = VisitAttachment
        fields = ['image']
        widgets = {
            # Attachment is OPTIONAL — the doctor / nurse must be able to
            # save the visit without uploading an image.
            #
            # NOTE: The doctor_complete_visit.html template renders TWO
            # separate `<input type="file">` elements directly (one with
            # `capture="environment"` for the camera, one with `multiple`
            # for the gallery) so the user can choose between them — and
            # the view reads files via `request.FILES.getlist(...)` so it
            # picks up however many were attached.
            #
            # This bound widget here is therefore only used by templates
            # that still render `{{ attachment_form.image }}` directly
            # (e.g. edit_visit.html). It must NOT carry `multiple=True`
            # because Django's ClearableFileInput refuses it
            # (ValueError at class-load time).
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make the image field optional at the form level.
        self.fields['image'].required = False
        # Defensive: ensure the rendered <input> doesn't carry `required`.
        self.fields['image'].widget.attrs.pop('required', None)


# -----------------------------------------------------------------------------
# Appointment form — used by the "احجز موعد" button on the patient page.
# -----------------------------------------------------------------------------
class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['scheduled_at', 'appt_type', 'notes']
        labels = {
            'scheduled_at': 'تاريخ ووقت الموعد',
            'appt_type':    'نوع الموعد',
            'notes':        'ملاحظات',
        }
        widgets = {
            'scheduled_at': forms.DateTimeInput(
                attrs={'class': 'form-control', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'appt_type': forms.Select(attrs={'class': 'form-control'}),
            'notes':     forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Accept HTML5 datetime-local format in addition to Django defaults.
        self.fields['scheduled_at'].input_formats = [
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M',
        ]


class SignupRequestForm(forms.ModelForm):
    class Meta:
        model = SignupRequest
        fields = [
            "clinic_name",
            "clinic_specialty",
            "doctor_name",
            "doctor_phone",
            "doctor_email",
            "nurse_name",
            "nurse_phone",
            "city",
            "notes",
        ]
        labels = {
            'clinic_name': 'اسم العيادة',
            'clinic_specialty': 'تخصص العيادة',
            'doctor_name': 'اسم الطبيب',
            'doctor_phone': 'رقم هاتف الطبيب',
            'doctor_email': 'البريد الإلكتروني للطبيب',
            'nurse_name': 'اسم الممرض (اختياري)',
            'nurse_phone': 'رقم هاتف الممرض (اختياري)',
            'city': 'المدينة أو المنطقة',
            'notes': 'ملاحظات إضافية (اختياري)',
        }
        widgets = {
            'clinic_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أدخل اسم العيادة'}),
            'clinic_specialty': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أدخل تخصص العيادة'}),
            'doctor_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أدخل اسم الطبيب'}),
            'doctor_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم هاتف الطبيب للتواصل'}),
            'doctor_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'example@email.com', 'required': 'required'}),
            'nurse_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أدخل اسم الممرض إن وجد'}),
            'nurse_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم هاتف الممرض'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'المدينة أو المنطقة/اسم الشارع'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'أي تفاصيل أو أوقات مفضلة للتواصل...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Doctor email is mandatory at the form level. The model's EmailField
        # is non-null already, but we set required=True explicitly so the
        # browser shows a clear validation message before submit.
        self.fields['doctor_email'].required = True
        # The HTML5 `required` attribute is the safety net for non-JS
        # browsers — keep it on even if the parent template forgets it.
        self.fields['doctor_email'].widget.attrs['required'] = 'required'
