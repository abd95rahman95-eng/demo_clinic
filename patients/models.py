
from django.db import models
from django.contrib.auth.models import User

class Clinic(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name
    
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)

    def __str__(self):
        return self.user.username

class Patient(models.Model):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    age = models.IntegerField()
    phone = models.CharField(max_length=20)
    address = models.CharField(max_length=255, blank=True) 
    file_number = models.CharField(max_length=50)

    def save(self, *args, **kwargs):
        if not self.file_number:
            START_NUMBER = 1723  # 👈 رقم معرف العيادة

            last_patient = Patient.objects.order_by('-id').first()

            if last_patient:
                next_number = START_NUMBER + last_patient.id
            else:
                next_number = START_NUMBER

            self.file_number = f"FILE-{next_number}"

        super().save(*args, **kwargs)
    def __str__(self):
        return self.name
    



class Visit(models.Model):
    VISIT_TYPE_CHOICES = [
        ('first_visit', 'أول زيارة'),
        ('follow_up', 'مراجعة'),
        ('emergency', 'إسعاف'),
        ('consultation', 'استشارة'),
    ]

    STATUS_CHOICES = [
        ('nurse_draft', 'مسودة تمريض'),
        ('doctor_completed', 'مكتملة من الطبيب'),
    ]

    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='visits')
    clinic = models.ForeignKey('Clinic', on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_visits')
    assigned_doctor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_visits'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='nurse_draft')
    visit_type = models.CharField(max_length=20, choices=VISIT_TYPE_CHOICES)

    chief_complaint = models.TextField(blank=True)
    nursing_notes = models.TextField(blank=True)

    blood_pressure = models.CharField(max_length=20, blank=True)
    pulse = models.CharField(max_length=20, blank=True)
    temperature = models.CharField(max_length=20, blank=True)
    weight = models.CharField(max_length=20, blank=True)
    height = models.CharField(max_length=20, blank=True)
    blood_sugar = models.CharField(max_length=20, blank=True)

    history_of_present_illness = models.TextField(blank=True)
    clinical_examination = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    treatment_plan = models.TextField(blank=True)
    prescription = models.TextField(blank=True)
    lab_requests = models.TextField(blank=True)
    imaging_requests = models.TextField(blank=True)
    patient_instructions = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    doctor_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"زيارة {self.patient.name} - {self.get_status_display()}"