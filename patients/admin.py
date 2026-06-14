from django.contrib import admin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse
from .models import Clinic, Patient, UserProfile, Visit, SignupRequest, ToothCondition, Notification
from django.utils import timezone

admin.site.register(UserProfile)
admin.site.register(Patient)
admin.site.register(Visit)


# ── Re-register Django's built-in User admin with two extras ────────────
#   1. A filter "حالة الربط" that shows orphan users (no UserProfile)
#   2. Extra columns: clinic name, role, has-profile flag
# This replaces auth.UserAdmin so search/sorting still work like before.
from django.contrib.auth.admin import UserAdmin as _DjangoUserAdmin


class HasProfileFilter(admin.SimpleListFilter):
    """Filter the user list by whether they're connected to a UserProfile.
    Orphan users typically need to be assigned to a clinic OR deleted."""
    title = 'حالة الربط بالعيادة'
    parameter_name = 'has_profile'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'مرتبط بعيادة'),
            ('no',  'غير مرتبط (يتيم)'),
        )

    def queryset(self, request, qs):
        if self.value() == 'yes':
            return qs.filter(userprofile__isnull=False)
        if self.value() == 'no':
            return qs.filter(userprofile__isnull=True)
        return qs


class CustomUserAdmin(_DjangoUserAdmin):
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'is_active',
        'clinic_display',
        'role_display',
        'profile_status',
    )
    list_filter = (
        HasProfileFilter,
        'is_active',
        'is_staff',
        'is_superuser',
        'groups',
    )

    def get_queryset(self, request):
        # Pre-fetch the related clinic so the changelist doesn't fire one
        # query per row. Also avoids the RelatedObjectDoesNotExist surprise
        # for orphan users — `.userprofile` becomes a populated cache hit
        # OR an explicit None when missing.
        qs = super().get_queryset(request)
        return qs.select_related('userprofile__clinic')

    @admin.display(description='العيادة')
    def clinic_display(self, obj):
        # Use a defensive lookup that returns None for orphan users instead
        # of raising RelatedObjectDoesNotExist. We display a plain Unicode
        # dash so there's no HTML rendering risk inside the changelist.
        profile = UserProfile.objects.filter(user=obj).select_related('clinic').first()
        if profile and profile.clinic_id and profile.clinic:
            return profile.clinic.name
        return '—'

    @admin.display(description='الدور')
    def role_display(self, obj):
        names = list(obj.groups.values_list('name', flat=True))
        return ', '.join(names) if names else '—'

    @admin.display(description='حالة الملف', boolean=True)
    def profile_status(self, obj):
        return UserProfile.objects.filter(user=obj).exists()


# Swap the default User admin for ours.
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


# ── UserProfile inline so each Clinic page lists who is wired to it ──────
class UserProfileInline(admin.TabularInline):
    """Lists every UserProfile attached to this clinic, with quick links to
    the underlying User. Read-only on purpose — to add staff to a clinic,
    edit the User and assign the profile from there."""
    model = UserProfile
    extra = 0
    can_delete = False
    fields = ('user', 'username_link', 'email_display', 'role_display', 'is_active_display')
    readonly_fields = ('username_link', 'email_display', 'role_display', 'is_active_display')

    @admin.display(description='اسم المستخدم')
    def username_link(self, obj):
        if not obj.user_id:
            return '—'
        url = reverse('admin:auth_user_change', args=[obj.user_id])
        return format_html('<a href="{}"><b>{}</b></a>', url, obj.user.username)

    @admin.display(description='البريد')
    def email_display(self, obj):
        return obj.user.email or '—'

    @admin.display(description='الدور')
    def role_display(self, obj):
        groups = list(obj.user.groups.values_list('name', flat=True))
        if not groups:
            return '—'
        return ', '.join(groups)

    @admin.display(description='نشط', boolean=True)
    def is_active_display(self, obj):
        return obj.user.is_active


@admin.register(ToothCondition)
class ToothConditionAdmin(admin.ModelAdmin):
    list_display = ("visit", "tooth_number", "surface", "condition", "updated_at")
    list_filter  = ("condition", "surface")
    search_fields = ("tooth_number", "visit__patient__name")
    ordering = ("-updated_at",)
# Register your models here.

@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = (
        "clinic_number",
        "name",
        "specialty_type",
        "subscription_period",
        "get_subscription_end",
        "trial_start",
        "get_trial_end",
        "trial_days_left",
        "account_status",
        "ai_credits",
        "ai_daily_used_display",
        "linked_users_count",
    )
    list_display_links = ("clinic_number", "name")
    list_editable = ("ai_credits",)
    list_filter = ("specialty", "subscription_period")
    # Search by clinic name OR clinic number — admins commonly know the
    # number ("1234-...") from a patient file and want to jump straight to
    # the clinic record.
    search_fields = ("name", "clinic_number", "specialty_type")
    ordering = ("-clinic_number",)
    inlines = [UserProfileInline]

    fieldsets = (
        ("بيانات العيادة", {
            "fields": (
                "name",
                "clinic_number",
                "specialty",
                "specialty_type",
                "address",
            ),
            "description": (
                "<b>specialty</b>: الحقل الداخلي الذي يحدد نموذج الحقول الطبية في النظام (لا تغيّره إلا عند تغيير الاختصاص الفعلي). "
                "<b>specialty_type</b>: النص الحر الذي سيراه الطاقم في صفحة "
                "\"إدارة الحساب\"."
            ),
        }),
        ("الاشتراك", {
            "fields": (
                "subscription_period",
                "subscription_start",
                "trial_start",
            ),
        }),
        ("المساعد الذكي (تحليلات)", {
            "fields": (
                "ai_credits",
                "ai_daily_used",
                "ai_last_reset",
            ),
            "description": (
                "يحصل كل عيادة على 3 تحليلات مجانية يومياً. "
                "أضف رصيداً مشترى عبر حقل \"رصيد التحليلات المشتراة\" "
                "(يُستهلك بعد انتهاء الحصة اليومية)."
            ),
        }),
    )

    @admin.display(description="استخدام اليوم")
    def ai_daily_used_display(self, obj):
        return f"{obj.ai_daily_used or 0}/{obj.AI_DAILY_FREE_LIMIT}"

    @admin.display(description="عدد المستخدمين")
    def linked_users_count(self, obj):
        # The reverse manager always exists on a Clinic instance so the
        # hasattr() guard was redundant — and bare numbers render fine
        # in the changelist without HTML wrapping.
        return UserProfile.objects.filter(clinic=obj).count()

    @admin.display(description="نهاية الاشتراك")
    def get_subscription_end(self, obj):
        from datetime import timedelta
        if not obj.subscription_start or not obj.subscription_period:
            return "—"
        if obj.subscription_period == '1_month':
            return obj.subscription_start + timedelta(days=30)
        elif obj.subscription_period == '1_year':
            return obj.subscription_start + timedelta(days=365)
        return "—"

    @admin.display(description="تاريخ النهاية")
    def get_trial_end(self, obj):
        from datetime import timedelta
        if not obj.trial_start:
            return "—"
        return obj.trial_start + timedelta(days=30)

    @admin.display(description="الأيام المتبقية")
    def trial_days_left(self, obj):
        from datetime import timedelta
        if not obj.trial_start:
            return "0 يوم"

        end_date = obj.trial_start + timedelta(days=30)
        delta = end_date - timezone.now().date()
        days = delta.days

        if days < 0:
            return "انتهى"
        return f"{days} يوم"

    @admin.display(description="حالة الحساب")
    def account_status(self, obj):
        if obj.is_active_subscription:
            return format_html(
                '<span style="padding:6px 10px;border-radius:999px;background:#15803d;color:white;">{}</span>',
                "نشط"
            )
        return format_html(
            '<span style="padding:6px 10px;border-radius:999px;background:#b91c1c;color:white;">{}</span>',
            "غير نشط / منتهي"
        )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Notification admin — usually staff manage notifications via the
    in-app page at /patients/notifications/admin/, but registering here
    gives Django superusers a fallback view.

    Kept intentionally minimal: the changelist uses only plain fields and
    safe display methods (no format_html, no M2M counts on the row) so
    it never crashes when a row has target_clinic = None (broadcast).
    """
    list_display = ("title", "target_label", "created_at")
    list_filter = ("target_clinic", "created_at")
    search_fields = ("title", "body")
    raw_id_fields = ("target_clinic",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        ("الإشعار", {
            "fields": ("title", "body", "url"),
        }),
        ("الاستهداف", {
            "fields": ("target_clinic",),
            "description": (
                "اتركه فارغاً لإرسال الإشعار لجميع العيادات (Broadcast). "
                "اختر عيادة محددة لتقييد ظهور الإشعار."
            ),
        }),
        ("بيانات النظام", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        # Pre-fetch the FK so the changelist doesn't fire one query per
        # row — also makes target_clinic access cheap & safe even when
        # the FK is NULL (broadcast).
        return super().get_queryset(request).select_related("target_clinic")

    @admin.display(description="المستهدف", ordering="target_clinic")
    def target_label(self, obj):
        # Plain text only — no format_html. Broadcast = "جميع العيادات".
        if obj.target_clinic_id and obj.target_clinic is not None:
            return obj.target_clinic.name
        return "جميع العيادات"


@admin.register(SignupRequest)
class SignupRequestAdmin(admin.ModelAdmin):
    list_display = (
        "clinic_name",
        "clinic_specialty",
        "doctor_name",
        "doctor_phone",
        "doctor_email",
        "status_badge",
        "created_at",
    )
    # When you open the admin index, the changelist link shows the total
    # count next to the model name. By ordering by created_at desc we put
    # fresh requests on top — combined with the email notification + the
    # status_badge below, ops gets multiple visual cues for new submissions.
    ordering = ("-created_at",)
    list_per_page = 25
    list_filter = ("status", "created_at", "city")
    search_fields = (
        "clinic_name",
        "doctor_name",
        "doctor_phone",
        "doctor_email",
        "nurse_name",
        "nurse_phone",
    )
    readonly_fields = ("created_at",)

    fieldsets = (
        ("بيانات العيادة", {
            "fields": ("clinic_name", "city", "status", "created_at")
        }),
        ("التخصص", {
            "fields": ("clinic_specialty",)
        }),
        ("بيانات الطبيب", {
            "fields": ("doctor_name", "doctor_phone", "doctor_email")
        }),
        ("بيانات الممرض", {
            "fields": ("nurse_name", "nurse_phone")
        }),
        ("معلومات إضافية", {
            "fields": ("notes",)
        }),
    )

    @admin.display(description="الحالة")
    def status_badge(self, obj):
        colors = {
            "new": "#b45309",
            "reviewed": "#1d4ed8",
            "approved": "#15803d",
            "rejected": "#b91c1c",
        }
        labels = {
            "new": "جديد",
            "reviewed": "تمت المراجعة",
            "approved": "تم",
            "rejected": "مرفوض",
        }
        color = colors.get(obj.status, "#475569")
        label = labels.get(obj.status, obj.status)
        return format_html(
            '<span style="padding:6px 10px;border-radius:999px;color:white;background:{};font-weight:600;">{}</span>',
            color,
            label,
        )
