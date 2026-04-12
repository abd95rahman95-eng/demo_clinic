
from django.db import models
from django.contrib.auth.models import User

SPECIALTY_CHOICES = [
    ('general_practice', 'General Practice'),
    ('cardiology',       'Cardiology'),
    ('orthopedics',      'Orthopedics'),
    ('neurology',        'Neurology'),
    ('dermatology',      'Dermatology'),
    ('gynecology',       'Gynecology & Obstetrics'),
    ('dentistry',        'Dentistry'),
]

PLAN_CHOICES = [
    ('basic', 'Basic'),
    ('pro',   'Pro'),
]

SUBSCRIPTION_CHOICES = [
    ('1_month', 'شهر واحد'),
    ('1_year', 'سنة واحدة'),
]

class Clinic(models.Model):
    name      = models.CharField(max_length=100)
    clinic_number = models.IntegerField(null=True, blank=True, unique=True, verbose_name="رقم العيادة")
    plan      = models.CharField(max_length=20, choices=PLAN_CHOICES, default='basic')
    subscription_period = models.CharField(max_length=20, choices=SUBSCRIPTION_CHOICES, blank=True, null=True, verbose_name='مدة الاشتراك')
    subscription_start = models.DateField(null=True, blank=True, verbose_name='تاريخ بداية الاشتراك')
    specialty = models.CharField(max_length=30, choices=SPECIALTY_CHOICES, default='general_practice')
    trial_start = models.DateField(null=True, blank=True)

    @property
    def is_pro(self):
        from datetime import date, timedelta
        if self.plan == 'pro':
            return True
        if self.trial_start:
            return date.today() < self.trial_start + timedelta(days=30)
        return False

    @property
    def is_active_subscription(self):
        from datetime import date, timedelta
        # 1. Check trial
        if self.trial_start and date.today() <= self.trial_start + timedelta(days=30):
            return True
            
        # 2. Check actual subscription
        if self.subscription_start and self.subscription_period:
            if self.subscription_period == '1_month':
                end_date = self.subscription_start + timedelta(days=30)
            elif self.subscription_period == '1_year':
                end_date = self.subscription_start + timedelta(days=365)
            else:
                return False
                
            if date.today() <= end_date:
                return True
                
        # If neither trial nor subscription is valid
        return False

    @property
    def subscription_days_left(self):
        from datetime import date, timedelta
        # 1. Check trial
        if self.trial_start and date.today() <= self.trial_start + timedelta(days=30):
            days_left = (self.trial_start + timedelta(days=30)) - date.today()
            return f"{days_left.days} يوم (فترة تجريبية)"
            
        # 2. Check actual subscription
        if self.subscription_start and self.subscription_period:
            if self.subscription_period == '1_month':
                end_date = self.subscription_start + timedelta(days=30)
            elif self.subscription_period == '1_year':
                end_date = self.subscription_start + timedelta(days=365)
            else:
                return "منتهي"
                
            if date.today() <= end_date:
                days_left = end_date - date.today()
                return f"{days_left.days} يوم"
                
        # If neither trial nor subscription is valid
        return "منتهي"

    @property
    def subscription_days_count(self):
        from datetime import date, timedelta
        if self.trial_start and date.today() <= self.trial_start + timedelta(days=30):
            return ((self.trial_start + timedelta(days=30)) - date.today()).days
            
        if self.subscription_start and self.subscription_period:
            if self.subscription_period == '1_month':
                end_date = self.subscription_start + timedelta(days=30)
            elif self.subscription_period == '1_year':
                end_date = self.subscription_start + timedelta(days=365)
            else:
                return 0
                
            if date.today() <= end_date:
                return (end_date - date.today()).days
                
        return 0

    def save(self, *args, **kwargs):
        if not self.clinic_number:
            last_clinic = Clinic.objects.exclude(clinic_number__isnull=True).order_by('-clinic_number').first()
            if last_clinic and last_clinic.clinic_number:
                self.clinic_number = last_clinic.clinic_number + 1
            else:
                self.clinic_number = 2601
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)

    def __str__(self):
        return self.user.username

class Patient(models.Model):
    GENDER_CHOICES = [
        ('Male', 'ذكر'),
        ('Female', 'أنثى'),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    age = models.IntegerField()
    phone = models.CharField(max_length=20)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    address = models.CharField(max_length=255, blank=True)
    file_number = models.CharField(max_length=50)

    def save(self, *args, **kwargs):
        if not self.file_number:
            clinic_num = self.clinic.clinic_number if self.clinic.clinic_number else 1723
            
            last_patient = Patient.objects.filter(clinic=self.clinic, file_number__startswith=f"{clinic_num}-").order_by('id').last()

            if last_patient and "-" in last_patient.file_number:
                try:
                    last_seq = int(last_patient.file_number.split('-')[1])
                    next_seq = last_seq + 1
                except ValueError:
                    next_seq = 1
            else:
                next_seq = 1

            self.file_number = f"{clinic_num}-{next_seq:04d}"

        super().save(*args, **kwargs)
    def __str__(self):
        return self.name
    


# 👈 نموذج الزيارة result added

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
    lab_results = models.TextField(blank=True)
    imaging_results = models.TextField(blank=True)
    
        # --- Cardiology ---
    ecg_results         = models.TextField(blank=True)
    ejection_fraction   = models.CharField(max_length=20, blank=True)
    cardiac_history     = models.TextField(blank=True)
    chest_pain_type     = models.CharField(max_length=100, blank=True)
    cardiac_medications = models.TextField(blank=True)

    # --- Orthopedics ---
    pain_location   = models.CharField(max_length=100, blank=True)
    pain_scale      = models.PositiveSmallIntegerField(null=True, blank=True)  # 1–10
    injury_history  = models.TextField(blank=True)
    range_of_motion = models.TextField(blank=True)
    xray_findings   = models.TextField(blank=True)

    # --- Gynecology & Obstetrics ---
    last_menstrual_period  = models.DateField(null=True, blank=True)
    cycle_regularity       = models.CharField(max_length=100, blank=True)
    obstetric_history      = models.TextField(blank=True)
    contraception_method   = models.CharField(max_length=100, blank=True)
    # Pregnancy follow-up
    gestational_age_weeks  = models.PositiveSmallIntegerField(null=True, blank=True)
    abdominal_circumference = models.CharField(max_length=20, blank=True)
    fundal_height          = models.CharField(max_length=20, blank=True)
    fetal_heart_rate       = models.CharField(max_length=20, blank=True)
    fetal_movement         = models.CharField(max_length=100, blank=True)
    fetal_position         = models.CharField(max_length=100, blank=True)
    ultrasound_notes       = models.TextField(blank=True)
    # --- Neurology ---
    CT_MRI_findings = models.TextField(blank=True)
    neurological_examination = models.TextField(blank=True)
    # --- Dermatology ---
    skin_examination = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"زيارة {self.patient.name} - {self.get_status_display()}"

class VisitAttachment(models.Model):
    visit       = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='attachments')
    image       = models.ImageField(upload_to='visit_images/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for {self.visit}"

class SignupRequest(models.Model):
    STATUS_NEW = "new"
    STATUS_REVIEWED = "reviewed"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_NEW, "جديد"),
        (STATUS_REVIEWED, "تمت المراجعة"),
        (STATUS_APPROVED, "تم إنشاء الحساب"),
        (STATUS_REJECTED, "مرفوض"),
    ]

    # بيانات العيادة
    clinic_name = models.CharField(max_length=255)
    clinic_specialty = models.CharField(max_length=255, default='عام')


    # بيانات الطبيب
    doctor_name = models.CharField(max_length=255)
    doctor_phone = models.CharField(max_length=20)
    doctor_email = models.EmailField()

    # بيانات الممرض (اختياري)
    nurse_name = models.CharField(max_length=255, blank=True)
    nurse_phone = models.CharField(max_length=20, blank=True)

    # معلومات إضافية
    city = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.clinic_name} - {self.doctor_name}"