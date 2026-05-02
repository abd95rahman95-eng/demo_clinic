"""
Django signal handlers for the patients app.

Currently:
  - Sends an email notification to ops whenever a new SignupRequest is
    submitted, so the team is alerted to follow up. Failures are caught
    and logged so a flaky SMTP server never breaks the public form.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from .models import SignupRequest

log = logging.getLogger(__name__)


@receiver(post_save, sender=SignupRequest)
def notify_new_signup_request(sender, instance, created, **kwargs):
    """When a new SignupRequest is created, email the ops inbox."""
    if not created:
        return

    recipients = getattr(settings, 'SIGNUP_NOTIFY_EMAILS', []) or []
    if not recipients:
        return

    subject = f'طلب اشتراك جديد — {instance.clinic_name}'
    admin_url = ''
    try:
        admin_url = reverse('admin:patients_signuprequest_change', args=[instance.id])
    except Exception:
        pass

    body_lines = [
        'وصلنا طلب اشتراك جديد عبر موقع عيادتك:',
        '',
        f'العيادة: {instance.clinic_name}',
        f'التخصص: {instance.clinic_specialty}',
        f'المدينة: {instance.city or "—"}',
        '',
        f'الطبيب: {instance.doctor_name}',
        f'الهاتف: {instance.doctor_phone}',
        f'البريد: {instance.doctor_email}',
        '',
        f'الممرض: {instance.nurse_name or "—"}',
        f'هاتف الممرض: {instance.nurse_phone or "—"}',
        '',
        f'ملاحظات: {instance.notes or "—"}',
        '',
        f'تاريخ الإرسال: {instance.created_at:%Y-%m-%d %H:%M}',
    ]
    if admin_url:
        body_lines.append('')
        body_lines.append(f'فتح الطلب في لوحة الإدارة: {admin_url}')

    try:
        send_mail(
            subject=subject,
            message='\n'.join(body_lines),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception as exc:
        # Never block form submission on a flaky SMTP server.
        log.warning('SignupRequest email notification failed: %s', exc)
