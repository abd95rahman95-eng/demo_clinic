from django import forms
from django.contrib.auth.models import User
from .models import Visit, UserProfile, Patient, VisitAttachment, SignupRequest
from .specialty_lists import (
    get_nursing_fields,
    get_specialty_medical_fields,
    ALL_NURSING_VITALS,
    ALL_SPECIALTY_MEDICAL_FIELDS,
)

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['name', 'age', 'phone','gender', 'address']
        labels = {
            'name': 'الاسم',
            'age': 'العمر',
            'phone': 'رقم الهاتف',
            'gender': 'الجنس',
            'address': 'العنوان',
            
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'age': forms.NumberInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_age(self):
        age = self.cleaned_data.get('age')
        if age is not None and age < 0:
            raise forms.ValidationError("العمر يجب أن يكون رقمًا.")
        return age
    def clean_gender(self):
        gender = self.cleaned_data.get('gender')
        if gender not in ['Male', 'Female']:
            raise forms.ValidationError("الجنس يجب أن يكون ذكر أو أنثى.")
        return gender
    
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
            'prescription': 'الوصفة',
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
            'prescription': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
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
            # save the visit without uploading an image. We strip the HTML
            # `required` attribute as well as setting required=False on the
            # form field below.
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make the image field optional at the form level.
        self.fields['image'].required = False
        # Defensive: ensure the rendered <input> doesn't carry `required`.
        self.fields['image'].widget.attrs.pop('required', None)


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
            'doctor_email': 'البريد الإلكتروني للطبيب (اختياري)',
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
            'doctor_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'example@email.com'}),
            'nurse_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أدخل اسم الممرض إن وجد'}),
            'nurse_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم هاتف الممرض'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: الرقة, شارع 23 شباط'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'أي تفاصيل أو أوقات مفضلة للتواصل...'}),
        }
