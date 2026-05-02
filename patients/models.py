
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

SUBSCRIPTION_CHOICES = [
    ('1_month', 'شهر واحد'),
    ('1_year', 'سنة واحدة'),
]

class Clinic(models.Model):
    # ── AI assistance daily free quota (per clinic) ────────────────────────
    AI_DAILY_FREE_LIMIT = 3

    name      = models.CharField(max_length=100)
    clinic_number = models.IntegerField(null=True, blank=True, unique=True, verbose_name="رقم العيادة")
    # NOTE: 'plan' column kept (NOT NULL in DB) but no longer used in app logic.
    plan      = models.CharField(max_length=20, default='basic', editable=False)
    subscription_period = models.CharField(max_length=20, choices=SUBSCRIPTION_CHOICES, blank=True, null=True, verbose_name='مدة الاشتراك')
    subscription_start = models.DateField(null=True, blank=True, verbose_name='تاريخ بداية الاشتراك')

    # `specialty` is the internal enum used to drive the form field manifests
    # in specialty_lists.py — KEEP IT untouched. `specialty_type` is a free
    # text label shown to clinic staff (e.g. on the account page) so the
    # clinic can display its actual practice description, which doesn't have
    # to map 1:1 to one of the SPECIALTY_CHOICES values.
    specialty = models.CharField(max_length=30, choices=SPECIALTY_CHOICES, default='general_practice')
    specialty_type = models.CharField(
        max_length=120, blank=True, default='',
        verbose_name='التخصص (نص حر)',
        help_text='النص الذي يظهر للطاقم في صفحة إدارة الحساب — مثال: "طب الأسرة" أو "أمراض القلب التداخلية".',
    )

    trial_start = models.DateField(null=True, blank=True)

    # ── AI usage tracking ──────────────────────────────────────────────────
    # Free uses consumed today (resets at midnight server time via
    # _reset_ai_daily_if_needed()). Purchased credits are consumed only
    # after the daily free quota is exhausted.
    ai_daily_used = models.PositiveIntegerField(default=0, verbose_name="الاستخدام اليومي للذكاء الاصطناعي")
    ai_last_reset = models.DateField(null=True, blank=True, verbose_name="آخر تصفير لعدّاد اليوم")
    ai_credits = models.PositiveIntegerField(default=0, verbose_name="رصيد التحليلات المشتراة")

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

    # -------------------------------------------------------------------
    # AI usage helpers
    # -------------------------------------------------------------------
    def _reset_ai_daily_if_needed(self):
        """Roll the daily-used counter back to zero on a new calendar day."""
        from datetime import date as _date
        today = _date.today()
        if self.ai_last_reset != today:
            self.ai_daily_used = 0
            self.ai_last_reset = today
            return True
        return False

    @property
    def ai_daily_remaining(self):
        from datetime import date as _date
        today = _date.today()
        if self.ai_last_reset != today:
            return self.AI_DAILY_FREE_LIMIT
        return max(0, self.AI_DAILY_FREE_LIMIT - (self.ai_daily_used or 0))

    def consume_ai_usage(self):
        """Consume one AI generation. Free daily quota is used first, then
        purchased credits. Returns a dict with the outcome.

        Returns:
            {
                'ok': True/False,
                'source': 'daily' | 'credit' | None,
                'daily_remaining': int,
                'credits_remaining': int,
                'limit_reached': bool,
            }
        """
        # Always start by checking calendar rollover so the free quota is
        # accurate even on the first call of a new day.
        self._reset_ai_daily_if_needed()

        # 1) Free daily quota first.
        if (self.ai_daily_used or 0) < self.AI_DAILY_FREE_LIMIT:
            self.ai_daily_used = (self.ai_daily_used or 0) + 1
            self.save(update_fields=['ai_daily_used', 'ai_last_reset'])
            return {
                'ok': True,
                'source': 'daily',
                'daily_remaining': self.AI_DAILY_FREE_LIMIT - self.ai_daily_used,
                'credits_remaining': self.ai_credits or 0,
                'limit_reached': False,
            }

        # 2) Purchased credits.
        if (self.ai_credits or 0) > 0:
            self.ai_credits = self.ai_credits - 1
            self.save(update_fields=['ai_credits', 'ai_last_reset'])
            return {
                'ok': True,
                'source': 'credit',
                'daily_remaining': 0,
                'credits_remaining': self.ai_credits,
                'limit_reached': False,
            }

        # 3) Nothing left.
        return {
            'ok': False,
            'source': None,
            'daily_remaining': 0,
            'credits_remaining': self.ai_credits or 0,
            'limit_reached': True,
        }

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
    follow_up_date = models.DateTimeField(null=True, blank=True)
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

    # --- AI assistance ----------------------------------------------------
    # Last AI-generated medical suggestions for this visit. Saved at
    # generation time so the doctor can re-open the visit later and
    # review what the assistant produced (no need to re-spend a credit).
    ai_suggestions = models.TextField(blank=True, verbose_name="اقتراحات المساعد الذكي")
    ai_generated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"زيارة {self.patient.name} - {self.get_status_display()}"

class VisitAttachment(models.Model):
    # ── Compression settings ──────────────────────────────────────────
    # Longest-edge cap (px). Phone photos are often 4000+ px wide which is
    # way more than the chart needs — clamping to 1600 px on the longest
    # side cuts ~6× pixel area without visible quality loss in the UI.
    MAX_DIMENSION = 1600
    # JPEG quality used when re-encoding. 82 is the sweet spot — visually
    # near-lossless on photos while shrinking files dramatically.
    JPEG_QUALITY = 82
    # If the upload is already small enough we skip recompression to keep
    # the original bytes (e.g. an already-optimized scanned form).
    SKIP_THRESHOLD_BYTES = 200 * 1024  # 200 KB

    visit       = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='attachments')
    image       = models.ImageField(upload_to='visit_images/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """Resize & recompress the image before writing it to disk so that
        a 4 MB phone photo turns into ~200 KB without any change to how
        the rest of the app reads/serves it."""
        # Only run on first save (when a freshly-uploaded file is in
        # memory). On later saves, self.image is already a stored path.
        if self.image and not self.pk:
            try:
                self._compress_image_in_place()
            except Exception:
                # If compression fails for any reason (corrupt file,
                # unsupported format, missing PIL) we fall back to the
                # original bytes rather than blocking the upload.
                pass
        super().save(*args, **kwargs)

    def _compress_image_in_place(self):
        """Open self.image with PIL, downscale + re-encode to JPEG, and
        replace the in-memory file so Django stores the smaller version."""
        from io import BytesIO
        from PIL import Image, ImageOps
        from django.core.files.base import ContentFile
        import os as _os

        f = self.image
        # If file is already small AND its dimensions are reasonable we
        # leave it alone — saves a re-encode pass for already-optimized
        # uploads.
        try:
            if hasattr(f, 'size') and f.size and f.size <= self.SKIP_THRESHOLD_BYTES:
                # We still need to peek at dimensions; only skip if both
                # size AND dimensions are within budget.
                f.seek(0)
                with Image.open(f) as probe:
                    w, h = probe.size
                if max(w, h) <= self.MAX_DIMENSION:
                    f.seek(0)
                    return
        except Exception:
            pass

        f.seek(0)
        img = Image.open(f)

        # Honour EXIF orientation (phones tag rotation in EXIF instead of
        # actually rotating pixels — without this, portrait photos look
        # sideways after re-encoding).
        img = ImageOps.exif_transpose(img)

        # JPEG can't carry alpha. Flatten RGBA / P / LA over white so
        # transparent PNGs don't come out with a black background.
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new('RGB', img.size, (255, 255, 255))
            mask = img.convert('RGBA').split()[-1]
            background.paste(img.convert('RGB'), mask=mask)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Downscale only if larger than the cap. Image.thumbnail() keeps
        # the aspect ratio and only ever shrinks (never enlarges).
        if max(img.size) > self.MAX_DIMENSION:
            img.thumbnail(
                (self.MAX_DIMENSION, self.MAX_DIMENSION),
                Image.LANCZOS,
            )

        buf = BytesIO()
        img.save(
            buf,
            format='JPEG',
            quality=self.JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
        buf.seek(0)

        # Force a .jpg extension since we're re-encoding to JPEG.
        original_name = _os.path.basename(getattr(f, 'name', 'attachment'))
        stem, _ext = _os.path.splitext(original_name)
        new_name = (stem or 'attachment') + '.jpg'

        self.image.save(new_name, ContentFile(buf.read()), save=False)

    def __str__(self):
        return f"Attachment for {self.visit}"


# -----------------------------------------------------------------------------
# Dental chart — one row per (visit, tooth, surface).
# Used only for clinics with specialty == 'dentistry'.
# A new visit inherits the previous visit's chart (handled in views).
# -----------------------------------------------------------------------------
class ToothCondition(models.Model):
    # Adult permanent teeth (FDI numbering): 11–18, 21–28, 31–38, 41–48
    TOOTH_CHOICES = [(str(n), str(n)) for n in (
        list(range(11, 19)) + list(range(21, 29)) +
        list(range(31, 39)) + list(range(41, 49))
    )]

    SURFACE_CHOICES = [
        ('whole', 'كامل'),
        ('O',     'إطباقي'),     # Occlusal (posterior teeth only)
        ('M',     'إنسي'),       # Mesial
        ('D',     'وحشي'),       # Distal
        ('B',     'دهليزي/شفوي'),     # Buccal / Labial
        ('L',     'لساني/حنكي'),       # Lingual / Palatal
        # Single root (used for incisors, canines, premolars)
        ('R',     'جذر'),
        # Multi-root variants
        ('MR',    'جذر إنسي'),    # Mesial root  (lower molars + upper molars)
        ('DR',    'جذر وحشي'),    # Distal root  (lower molars + upper molars)
        ('PR',    'جذر حنكي'),    # Palatal root (upper molars only)
    ]

    CONDITION_CHOICES = [
        ('healthy',     'سليم'),
        ('caries',      'تسوس'),
        ('filling',     'حشوة'),
        ('crown',       'تلبيس'),
        ('rct',         'سحب عصب'),
        ('fracture',    'كسر'),
        ('missing',     'مفقود'),
        ('to_extract',  'يحتاج خلع'),
        ('to_treat',    'يحتاج معالجة'),
        ('implant',     'زرعة'),
        ('bridge',      'جسر'),
    ]

    visit        = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='tooth_conditions')
    tooth_number = models.CharField(max_length=2, choices=TOOTH_CHOICES)
    surface      = models.CharField(max_length=10, choices=SURFACE_CHOICES, default='whole')
    condition    = models.CharField(max_length=20, choices=CONDITION_CHOICES)
    note         = models.CharField(max_length=200, blank=True, default='')
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('visit', 'tooth_number', 'surface')
        indexes = [
            models.Index(fields=['visit']),
            models.Index(fields=['tooth_number']),
        ]

    def __str__(self):
        return f"Tooth {self.tooth_number}/{self.surface} = {self.condition} (visit {self.visit_id})"

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