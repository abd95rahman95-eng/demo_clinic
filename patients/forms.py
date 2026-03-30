from django import forms
from django.contrib.auth.models import User
from .models import Visit, UserProfile, Patient

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['name', 'age', 'phone', 'address']
        labels = {
            'name': 'الاسم',
            'age': 'العمر',
            'phone': 'رقم الهاتف',
            'address': 'العنوان',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'age': forms.NumberInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_age(self):
        age = self.cleaned_data.get('age')
        if age is not None and age < 0:
            raise forms.ValidationError("العمر يجب أن يكون رقمًا.")
        return age


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

    def clean_assigned_doctor(self):
        doctor = self.cleaned_data.get('assigned_doctor')
        if not doctor:
            raise forms.ValidationError("لا يوجد طبيب متاح في هذه العيادة.")
        return doctor


class DoctorVisitForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = [
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
            'lab_results',
            'imaging_results',
        ]
        labels = {
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
            'lab_results': 'نتائج التحاليل',
            'imaging_results': 'نتائج الصور',
        }
        widgets = {
            'history_of_present_illness': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'clinical_examination': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'diagnosis': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'treatment_plan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'prescription': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'lab_requests': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'imaging_requests': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'patient_instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'follow_up_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'doctor_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'lab_results': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'imaging_results': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }