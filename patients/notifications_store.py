"""
JSON-file backed notifications store.

Why a file (not a model)?
-------------------------
The project rules forbid new migrations, so we keep notifications outside
the DB schema. The bell widget in the navbar is read-heavy and very low
volume (a handful of broadcasts per week, at most), so a single JSON file
under MEDIA_ROOT is perfectly adequate.

File layout
-----------
The store is one JSON file at MEDIA_ROOT/notifications.json with shape:

    {
        "notifications": [
            {
                "id": "abc123",                 # short stable id
                "title": "تحديث جديد",
                "body":  "تم إضافة ميزة...",
                "url":   "/account/",           # optional click-through
                "created_at": "2026-05-09T10:30",
                "target_clinic_id": null,        # null = broadcast to all
                "read_by_clinic_ids": [12, 45]
            },
            ...
        ]
    }

Concurrency
-----------
Reads + writes are short, single-process by default (Render dyno = 1
worker for small clinics). We use a tiny file-level lock around writes
so concurrent admin actions don't clobber each other.

Idea / future:
    - Move to a real Notification model when migrations become allowed.
    - Add per-user read tracking (we currently track per-clinic).
    - Add categories (info / warning / billing) and filter in the bell.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime
from pathlib import Path

from django.conf import settings


# A single in-process lock is enough for the typical small Render
# deployment. If we ever scale to multiple workers we should swap this
# for an OS-level file lock (e.g. fcntl) — flagged here for future.
_lock = threading.Lock()


def _store_path() -> Path:
    media_root = Path(getattr(settings, 'MEDIA_ROOT', Path('.')))
    media_root.mkdir(parents=True, exist_ok=True)
    return media_root / 'notifications.json'


def _read_raw() -> dict:
    """Load the JSON file. Returns an empty default if missing/corrupt."""
    path = _store_path()
    if not path.exists():
        return {'notifications': []}
    try:
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, dict) or 'notifications' not in data:
                return {'notifications': []}
            return data
    except (OSError, ValueError):
        # Corrupt file — never blow up the bell. Returning empty
        # behaves like "no notifications" which is safe.
        return {'notifications': []}


def _write_raw(data: dict) -> None:
    """Atomic-ish write: write to a temp file then rename."""
    path = _store_path()
    tmp = path.with_suffix('.json.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ── Public API ──────────────────────────────────────────────────────────

def add_notification(*, title: str, body: str = '', url: str = '',
                     target_clinic_id: int | None = None) -> dict:
    """Append a new notification. `target_clinic_id=None` means broadcast.

    Returns the saved notification dict (with its generated id).
    """
    notif = {
        'id': secrets.token_hex(6),
        'title': str(title or '').strip(),
        'body':  str(body or '').strip(),
        'url':   str(url or '').strip(),
        'created_at': datetime.now().isoformat(timespec='minutes'),
        'target_clinic_id': target_clinic_id,
        'read_by_clinic_ids': [],
    }
    with _lock:
        data = _read_raw()
        data['notifications'].insert(0, notif)
        # Hard cap so the file never balloons. 200 is plenty for a bell.
        data['notifications'] = data['notifications'][:200]
        _write_raw(data)
    return notif


def get_notifications_for_clinic(clinic_id: int, limit: int = 10) -> list[dict]:
    """Return the latest `limit` notifications visible to this clinic
    (broadcasts + ones explicitly targeted at them), with an extra
    `read` flag based on `read_by_clinic_ids`.
    """
    if not clinic_id:
        return []
    data = _read_raw()
    out = []
    for n in data['notifications']:
        target = n.get('target_clinic_id')
        if target is not None and int(target) != int(clinic_id):
            continue
        out.append({
            **n,
            'read': int(clinic_id) in (n.get('read_by_clinic_ids') or []),
        })
        if len(out) >= limit:
            break
    return out


def unread_count_for_clinic(clinic_id: int) -> int:
    """How many of the visible notifications haven't been seen yet."""
    if not clinic_id:
        return 0
    data = _read_raw()
    count = 0
    for n in data['notifications']:
        target = n.get('target_clinic_id')
        if target is not None and int(target) != int(clinic_id):
            continue
        if int(clinic_id) not in (n.get('read_by_clinic_ids') or []):
            count += 1
    return count


def mark_all_read_for_clinic(clinic_id: int) -> int:
    """Mark every visible notification as read for this clinic.
    Returns the number of notifications updated."""
    if not clinic_id:
        return 0
    updated = 0
    with _lock:
        data = _read_raw()
        for n in data['notifications']:
            target = n.get('target_clinic_id')
            if target is not None and int(target) != int(clinic_id):
                continue
            read_list = n.setdefault('read_by_clinic_ids', [])
            if int(clinic_id) not in read_list:
                read_list.append(int(clinic_id))
                updated += 1
        if updated:
            _write_raw(data)
    return updated


def mark_one_read_for_clinic(clinic_id: int, notif_id: str) -> bool:
    """Mark a single notification as read for this clinic. Returns True
    if a row was actually updated."""
    if not clinic_id or not notif_id:
        return False
    with _lock:
        data = _read_raw()
        for n in data['notifications']:
            if n.get('id') != notif_id:
                continue
            target = n.get('target_clinic_id')
            if target is not None and int(target) != int(clinic_id):
                return False
            read_list = n.setdefault('read_by_clinic_ids', [])
            if int(clinic_id) in read_list:
                return False
            read_list.append(int(clinic_id))
            _write_raw(data)
            return True
    return False
