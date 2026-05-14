"""Restore the truncated tail of patients/views.py.

The file ended with a dangling `if next_url:` in the middle of
`cancel_appointment`. We find the @login_required/@require_POST/def
cancel_appointment header on disk, drop everything from that point on,
and rewrite the full cancel_appointment + print_prescription tail.
"""
from pathlib import Path

ROOT = Path('/sessions/loving-cool-cannon/mnt/demo_clinic/patients')

VIEWS_TAIL_LINES = [
    "@login_required(login_url='login')",
    "@require_POST",
    "def cancel_appointment(request, appointment_id):",
    '    """Mark an appointment as cancelled. Reachable from the calendar view."""',
    "    if not (is_doctor(request.user) or is_nurse(request.user)):",
    "        return redirect('dashboard')",
    "    profile = UserProfile.objects.get(user=request.user)",
    "    appt = get_object_or_404(Appointment, id=appointment_id, clinic=profile.clinic)",
    "    appt.status = 'cancelled'",
    "    appt.save(update_fields=['status', 'updated_at'])",
    '    messages.success(request, "تم إلغاء الموعد.")',
    "    next_url = request.POST.get('next')",
    "    if next_url:",
    "        return redirect(next_url)",
    "    return redirect('calendar')",
    "",
    "",
    "# -----------------------------------------------------------------------------",
    "# A5 prescription print",
    "# -----------------------------------------------------------------------------",
    "@login_required(login_url='login')",
    "def print_prescription(request, visit_id):",
    '    """Render an A5-formatted prescription for a single visit. Designed to',
    "    auto-open the browser print dialog. Only available to doctors inside the",
    '    same clinic."""',
    "    if not is_doctor(request.user):",
    "        return redirect('dashboard')",
    "",
    "    profile = UserProfile.objects.get(user=request.user)",
    "    visit = get_object_or_404(Visit, id=visit_id, clinic=profile.clinic)",
    "",
    "    # Decode structured prescription rows if present.",
    "    items = []",
    "    raw_items = (visit.prescription_items or '').strip()",
    "    if raw_items:",
    "        try:",
    "            decoded = _json_specs.loads(raw_items)",
    "            if isinstance(decoded, list):",
    "                items = [r for r in decoded if isinstance(r, dict) and r.get('name')]",
    "        except Exception:",
    "            items = []",
    "",
    "    # Doctor display name + specialty text-form (clinic.specialty_type takes",
    "    # precedence over the internal enum so the doctor sees the wording the",
    "    # admin set on the account page).",
    "    clinic = visit.clinic",
    "    specialty_label = (clinic.specialty_type or '').strip() or clinic.get_specialty_display()",
    '    doctor_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username',
    "",
    "    return render(request, 'patients/print_prescription.html', {",
    "        'visit': visit,",
    "        'patient': visit.patient,",
    "        'clinic': clinic,",
    "        'items': items,",
    "        'free_text': (visit.prescription or '').strip(),",
    "        'specialty_label': specialty_label,",
    "        'doctor_name': doctor_name,",
    "    })",
    "",
    "",
    "# end of views.py",
    "",
]
VIEWS_TAIL = '\r\n'.join(VIEWS_TAIL_LINES).encode('utf-8')


def fix_views():
    p = ROOT / 'views.py'
    data = p.read_bytes()
    needle = b'@login_required(login_url=\'login\')\r\n@require_POST\r\ndef cancel_appointment'
    idx = data.find(needle)
    if idx == -1:
        needle = b'@login_required(login_url=\'login\')\n@require_POST\ndef cancel_appointment'
        idx = data.find(needle)
    if idx == -1:
        raise SystemExit('Could not locate cancel_appointment header — aborting.')
    new = data[:idx] + VIEWS_TAIL
    p.write_bytes(new)
    print(f'views.py rewritten: idx={idx} new_size={len(new)} (old_size={len(data)})')


if __name__ == '__main__':
    fix_views()
