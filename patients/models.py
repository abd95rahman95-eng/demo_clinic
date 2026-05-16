
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
    # `age` is kept on the model for backward-compat with old data and existing
    # display loops. New records compute age from `birth_date` (see `.age_years`
    # property). The field is nullable so a freshly added patient that only has
    # a birth_date doesn't need a redundant int stored.
    age = models.IntegerField(null=True, blank=True)
    # Source of truth for age going forward. If the clinic doesn't know the
    # exact month/day, the form defaults them to 1/1 (January 1st of the
    # provided birth year).
    birth_date = models.DateField(null=True, blank=True, verbose_name='تاريخ الميلاد')
    phone = models.CharField(max_length=20)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    address = models.CharField(max_length=255, blank=True)
    file_number = models.CharField(max_length=50)

    @property
    def age_years(self):
        """Computed age in whole years. Prefers birth_date (auto-updates each
        year) and falls back to the legacy `age` int for patients added
        before the birth_date column existed."""
        from datetime import date as _date
        if self.birth_date:
            today = _date.today()
            years = today.year - self.birth_date.year
            # Subtract 1 if we haven't reached the birthday yet this year.
            if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
                years -= 1
            return max(0, years)
        return self.age

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
        # New "half-completed" status used by the doctor's
        # "حفظ كاستشارة" save mode. Visit is saved but flagged
        # as needing referral (specialist, lab, imaging) — shown
        # to staff as in-progress and listed under "زيارات الاستشارة"
        # on the dashboard.
        ('consultation_pending', 'استشارة قيد الانتظار'),
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
    # Structured prescription. Stored as JSON-encoded list of rows:
    # [{"name": "...", "dose": "...", "frequency": "...", "duration": "...", "notes": "..."}, ...]
    # The free-text `prescription` field above is kept for backward-compat
    # and to capture anything the doctor wants outside the structured rows.
    # The A5 print template renders from `prescription_items` first and falls
    # back to `prescription` if no structured rows exist.
    prescription_items = models.TextField(blank=True, default='', verbose_name='وصفة الأدوية (جدولية)')
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

class Notification(models.Model):
    """In-app notifications shown in the navbar bell.

    A notification with `target_clinic = None` is a broadcast — every
    clinic sees it. A notification with a specific `target_clinic` is
    only visible to that clinic. The `read_by_clinics` M2M tracks which
    clinics have already seen each notification (so the unread badge
    counter only counts what's actually unread).
    """
    title = models.CharField(max_length=200, verbose_name='العنوان')
    body  = models.TextField(blank=True, default='', verbose_name='المحتوى')
    url   = models.CharField(
        max_length=500, blank=True, default='',
        verbose_name='رابط (اختياري)',
        help_text='رابط داخلي أو خارجي يفتح عند الضغط على الإشعار.',
    )
    target_clinic = models.ForeignKey(
        'Clinic',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='targeted_notifications',
        verbose_name='العيادة المستهدفة',
        help_text='اتركه فارغاً لإرسال الإشعار لجميع العيادات.',
    )
    read_by_clinics = models.ManyToManyField(
        'Clinic',
        blank=True,
        related_name='read_notifications',
        verbose_name='قُرأ من قِبل',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'إشعار'
        verbose_name_plural = 'الإشعارات'

    def __str__(self):
        if self.target_clinic_id:
            return f'{self.title} → {self.target_clinic}'
        return f'{self.title} (broadcast)'

    @property
    def is_broadcast(self) -> bool:
        return self.target_clinic_id is None


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


# -----------------------------------------------------------------------------
# Appointment — independent booking model (NOT tied to Visit.follow_up_date).
#
# Used by the "احجز موعد" button on the patient page and by the new dashboard
# Calendar card. A booked appointment doesn't need an associated Visit row —
# the clinic creates a Visit (and the nurse_draft → doctor_completed flow)
# only when the patient actually walks in.
# -----------------------------------------------------------------------------
class Appointment(models.Model):
    APPT_TYPE_CHOICES = [
        ('follow_up',    'مراجعة'),
        ('first_visit',  'زيارة أولى'),
        ('consultation', 'استشارة'),
        ('procedure',    'إجراء / معالجة'),
        ('other',        'أخرى'),
    ]
    STATUS_CHOICES = [
        ('scheduled', 'مجدول'),
        ('done',      'تم'),
        ('cancelled', 'ملغى'),
    ]

    clinic       = models.ForeignKey('Clinic', on_delete=models.CASCADE, related_name='appointments')
    patient      = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='appointments')
    scheduled_at = models.DateTimeField(verbose_name='موعد الزيارة')
    appt_type    = models.CharField(max_length=20, choices=APPT_TYPE_CHOICES, default='follow_up', verbose_name='نوع الموعد')
    notes        = models.TextField(blank=True, default='', verbose_name='ملاحظات')
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    created_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='booked_appointments')
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('scheduled_at',)
        indexes = [
            models.Index(fields=['clinic', 'scheduled_at']),
            models.Index(fields=['patient']),
        ]

    def __str__(self):
        return f"موعد {self.patient.name} - {self.scheduled_at:%Y-%m-%d %H:%M}"

# =============================================================================
# Dental: examination + treatment planning + per-visit procedures (v2)
# =============================================================================
#
# This is the new mode-driven dental data layer that replaces the old
# `ToothCondition` model for the chart UI. ToothCondition is kept in the
# codebase for any legacy data + back-compat with `update_tooth_condition`
# endpoint, but the new 3D chart writes to the models below.
#
#   * ToothStatus     -- current "what does the mouth look like" snapshot
#                        (one row per patient * tooth * surface/root). Persists
#                        across visits; the latest examination wins.
#   * TreatmentPlan   -- a treatment plan for a patient (collection of steps).
#   * PlanStep        -- one planned procedure (tooth + surface + procedure
#                        type + priority + sequence). status: pending/done.
#   * VisitProcedure  -- an actual procedure performed during a visit. May
#                        link back to a PlanStep -- when set, the PlanStep is
#                        flipped to done and the plan's aggregate status
#                        recalculated.
#
# Shared choices live at module level so views, forms, and templates can
# reach them without instantiating a model.
# -----------------------------------------------------------------------------

DENTAL_SURFACE_CHOICES = [
    ('whole', 'كامل'),
    ('O',     'إطباقي'),
    ('M',     'إنسي'),
    ('D',     'وحشي'),
    ('B',     'دهليزي/شفوي'),
    ('L',     'لساني/حنكي'),
    ('R',     'جذر'),
    ('MR',    'جذر إنسي'),
    ('DR',    'جذر وحشي'),
    ('PR',    'جذر حنكي'),
]

DENTAL_TOOTH_CHOICES = [(str(n), str(n)) for n in (
    list(range(11, 19)) + list(range(21, 29)) +
    list(range(31, 39)) + list(range(41, 49))
)]

DENTAL_CONDITION_CHOICES = [
    ('healthy',          'سليم'),
    ('caries',           'تسوس'),
    ('existing_filling', 'حشوة موجودة'),
    ('existing_crown',   'تلبيس موجود'),
    ('existing_rct',     'سحب عصب سابق'),
    ('fracture',         'كسر'),
    ('wear',             'تآكل'),
    ('missing',          'مفقود'),
    ('implant',          'زرعة'),
    ('discoloration',    'تصبغ'),
]

DENTAL_PROCEDURE_CHOICES = [
    ('filling_composite', 'حشوة كومبوزيت'),
    ('filling_amalgam',   'حشوة أملغم'),
    ('rct',               'سحب عصب'),
    ('extraction',        'خلع'),
    ('crown',             'تلبيس'),
    ('crown_temp',        'تلبيس مؤقت'),
    ('bridge',            'جسر'),
    ('implant',           'زرعة'),
    ('cleaning',          'تنظيف وتلميع'),
    ('whitening',         'تبييض'),
    ('post_core',         'دعامة لبية'),
    ('other',             'أخرى'),
]


class ToothStatus(models.Model):
    """Current examination state of one tooth surface/root for one patient.

    There's at most one row per (patient, tooth, surface). The "Examination
    mode" of the chart writes here. `last_updated_visit` lets us reconstruct
    which visit introduced or last changed a given finding (used by the
    examination session-log view).
    """
    patient            = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='tooth_statuses')
    tooth_number       = models.CharField(max_length=2, choices=DENTAL_TOOTH_CHOICES)
    surface            = models.CharField(max_length=10, choices=DENTAL_SURFACE_CHOICES, default='whole')
    condition          = models.CharField(max_length=20, choices=DENTAL_CONDITION_CHOICES)
    note               = models.CharField(max_length=200, blank=True, default='')
    last_updated_visit = models.ForeignKey('Visit', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('patient', 'tooth_number', 'surface')
        indexes = [
            models.Index(fields=['patient']),
            models.Index(fields=['patient', 'tooth_number']),
        ]

    def __str__(self):
        return f"Status {self.patient_id} {self.tooth_number}/{self.surface} = {self.condition}"


class TreatmentPlan(models.Model):
    STATUS_CHOICES = [
        ('planned',     'مخطط'),
        ('in_progress', 'قيد التنفيذ'),
        ('completed',   'مكتمل'),
        ('cancelled',   'ملغى'),
    ]
    PRIORITY_CHOICES = [
        ('urgent',    'عاجل'),
        ('necessary', 'ضروري'),
        ('optional',  'اختياري'),
    ]

    patient    = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='treatment_plans')
    title      = models.CharField(max_length=200, blank=True, default='')
    priority   = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='necessary')
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    notes      = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"Plan #{self.pk} - {self.patient.name}"

    def recalc_status(self, commit=True):
        """Set status to planned / in_progress / completed based on step states.

        - All steps pending -> planned
        - Any step done but not all -> in_progress
        - All steps done -> completed
        - No steps -> planned (preserves cancelled if already cancelled)
        """
        if self.status == 'cancelled':
            return
        steps = list(self.steps.all())
        if not steps:
            new_status = 'planned'
        else:
            done = sum(1 for s in steps if s.status == 'done')
            if done == 0:
                new_status = 'planned'
            elif done == len(steps):
                new_status = 'completed'
            else:
                new_status = 'in_progress'
        if new_status != self.status:
            self.status = new_status
            if commit:
                self.save(update_fields=['status', 'updated_at'])


class PlanStep(models.Model):
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('done',    'تم'),
    ]

    plan         = models.ForeignKey(TreatmentPlan, on_delete=models.CASCADE, related_name='steps')
    tooth_number = models.CharField(max_length=2, choices=DENTAL_TOOTH_CHOICES)
    surface      = models.CharField(max_length=10, choices=DENTAL_SURFACE_CHOICES, default='whole')
    procedure    = models.CharField(max_length=30, choices=DENTAL_PROCEDURE_CHOICES)
    priority     = models.CharField(max_length=20, choices=TreatmentPlan.PRIORITY_CHOICES, default='necessary')
    sequence     = models.PositiveIntegerField(default=0)
    notes        = models.CharField(max_length=300, blank=True, default='')
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    canals       = models.CharField(
        max_length=120, blank=True, default='',
        help_text='Comma-separated canal codes for RCT, e.g. "MB,DB,P".',
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('sequence', 'created_at')
        indexes = [
            models.Index(fields=['plan']),
            models.Index(fields=['tooth_number']),
        ]

    def __str__(self):
        return f"Step #{self.pk} {self.tooth_number}/{self.surface} {self.procedure}"


class VisitProcedure(models.Model):
    """An actual procedure performed during a visit. The single source of truth
    for "what was done today". May reference a PlanStep -- when present, the
    PlanStep is auto-flipped to `done` and the parent plan is rechecked."""
    visit        = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='dental_procedures')
    plan_step    = models.ForeignKey(PlanStep, on_delete=models.SET_NULL, null=True, blank=True, related_name='procedures')
    tooth_number = models.CharField(max_length=2, choices=DENTAL_TOOTH_CHOICES)
    surface      = models.CharField(max_length=10, choices=DENTAL_SURFACE_CHOICES, default='whole')
    surfaces_csv = models.CharField(
        max_length=60, blank=True, default='',
        help_text='Comma-separated extra surfaces for multi-surface procedures, e.g. "O,M".',
    )
    procedure    = models.CharField(max_length=30, choices=DENTAL_PROCEDURE_CHOICES)
    material     = models.CharField(max_length=80, blank=True, default='')
    canals       = models.CharField(max_length=120, blank=True, default='')
    notes        = models.CharField(max_length=400, blank=True, default='')
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['visit']),
            models.Index(fields=['tooth_number']),
        ]

    def __str__(self):
        return f"Procedure #{self.pk} {self.tooth_number}/{self.surface} {self.procedure}"

    @property
    def all_surfaces(self):
        """Return the primary surface plus any extras from surfaces_csv."""
        extras = [s.strip() for s in (self.surfaces_csv or '').split(',') if s.strip()]
        return [self.surface] + [s for s in extras if s != self.surface]


class VisitPlanSnapshot(models.Model):
    """Frozen list of plan steps that were pending when a visit began.

    Created the first time the dental chart is opened for a visit. Lets
    the "End-of-visit summary" show "Planned for today" vs "Completed today"
    accurately even if the dentist creates new plan steps mid-visit (those
    wouldn't be in the snapshot, so they don't inflate the planned-for-today
    list).
    """
    visit      = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='plan_snapshots')
    plan_step  = models.ForeignKey(PlanStep, on_delete=models.CASCADE, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('visit', 'plan_step')
