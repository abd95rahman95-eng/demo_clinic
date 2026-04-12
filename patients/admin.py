from django.contrib import admin
from django.utils.html import format_html
from .models import Clinic, Patient, UserProfile, Visit, SignupRequest
from django.utils import timezone

admin.site.register(UserProfile)
admin.site.register(Patient)
admin.site.register(Visit)
# Register your models here.

@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "plan",
        "subscription_period",
        "get_subscription_end",
        "trial_start",
        "get_trial_end",
        "trial_days_left",
        "account_status",
    )

    @admin.display(description="نهاية الاشتراك (للأساسي)")
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
    list_filter = ("status", "created_at", "city")
    search_fields = (
        "clinic_name",
        "doctor_name",
        "doctor_phone",
        "doctor_email",
        "nurse_name",
        "nurse_phone",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    list_per_page = 25

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