/* ============================================================================
 * clinic_offline.js — IndexedDB-backed offline autosave + sync for visit forms.
 *
 * Behaviour:
 *   1. Every form marked with `data-offline` is autosaved to IndexedDB on
 *      every input/change (debounced) and on beforeunload / pagehide.
 *   2. When the user reopens a page that has a saved draft, a banner offers
 *      to restore or discard it. Restored file blobs are kept in JS state
 *      and re-attached on submit (browser security forbids programmatic
 *      population of <input type="file">).
 *   3. If the form is submitted while offline, the submission is queued in
 *      IndexedDB. When the browser comes back online, queued items are
 *      replayed automatically.
 *   4. A small online/offline status pill appears at the top-left when the
 *      browser loses connectivity, plus toasts confirm save / sync events.
 *
 * Key shape in IndexedDB:
 *   drafts: { formKey, pathname, savedAt, fields: {name: value|values},
 *             files: [{inputName, fileName, type, blob}] }
 *   queue:  { id (auto), url, method, formKey, fields, files, queuedAt }
 *
 * The script is self-contained: no external dependencies, uses native
 * IndexedDB. Designed to no-op gracefully on browsers without IndexedDB.
 * ========================================================================== */
(function () {
    'use strict';

    // ── Configuration ───────────────────────────────────────────────────────
    var DB_NAME       = 'clinic_offline_v1';
    var DB_VERSION    = 1;
    var STORE_DRAFTS  = 'drafts';
    var STORE_QUEUE   = 'queue';
    var SAVE_DEBOUNCE = 800;                     // ms
    var DRAFT_TTL_MS  = 14 * 24 * 60 * 60 * 1000; // 14 days

    // Skip auxiliary forms that should never be autosaved (search, delete
    // confirmations, AJAX appointment-clear forms, etc.). The user opted
    // in by adding `data-offline` to the form, so we just respect that.

    // ── IndexedDB helpers ───────────────────────────────────────────────────
    function openDB() {
        return new Promise(function (resolve, reject) {
            var req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function (e) {
                var db = e.target.result;
                if (!db.objectStoreNames.contains(STORE_DRAFTS)) {
                    db.createObjectStore(STORE_DRAFTS, { keyPath: 'formKey' });
                }
                if (!db.objectStoreNames.contains(STORE_QUEUE)) {
                    db.createObjectStore(STORE_QUEUE,
                        { keyPath: 'id', autoIncrement: true });
                }
            };
            req.onsuccess = function () { resolve(req.result); };
            req.onerror   = function () { reject(req.error); };
        });
    }

    function withStore(storeName, mode, fn) {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                var t = db.transaction(storeName, mode);
                var s = t.objectStore(storeName);
                var inner;
                try { inner = fn(s); } catch (e) { reject(e); return; }
                t.oncomplete = function () {
                    if (inner && typeof inner.result !== 'undefined') {
                        resolve(inner.result);
                    } else {
                        resolve(inner);
                    }
                };
                t.onerror = function () { reject(t.error); };
                t.onabort = function () { reject(t.error); };
            });
        });
    }

    function putDraft(d)   { return withStore(STORE_DRAFTS, 'readwrite', function (s) { return s.put(d); }); }
    function getDraft(k)   { return withStore(STORE_DRAFTS, 'readonly',  function (s) { return s.get(k); }); }
    function delDraft(k)   { return withStore(STORE_DRAFTS, 'readwrite', function (s) { return s.delete(k); }); }
    function enqueue(item) { return withStore(STORE_QUEUE,  'readwrite', function (s) { return s.add(item); }); }
    function listQueue()   { return withStore(STORE_QUEUE,  'readonly',  function (s) { return s.getAll(); }); }
    function delQueue(id)  { return withStore(STORE_QUEUE,  'readwrite', function (s) { return s.delete(id); }); }

    function cleanupStaleDrafts() {
        var cutoff = Date.now() - DRAFT_TTL_MS;
        openDB().then(function (db) {
            var t = db.transaction(STORE_DRAFTS, 'readwrite');
            var s = t.objectStore(STORE_DRAFTS);
            s.openCursor().onsuccess = function (e) {
                var c = e.target.result;
                if (!c) return;
                if (!c.value || (c.value.savedAt || 0) < cutoff) c.delete();
                c.continue();
            };
        }).catch(function () {});
    }

    // ── Form (de)serialization ─────────────────────────────────────────────
    function serializeForm(form) {
        var fields = {};
        var files  = [];
        var els = form.querySelectorAll('input, select, textarea');
        els.forEach(function (el) {
            if (!el.name) return;
            if (el.type === 'submit' || el.type === 'button') return;
            if (el.disabled) return;
            // CSRF is intentionally re-read at sync time from the cookie,
            // not stored — Django rotates it on login/logout.
            if (el.name === 'csrfmiddlewaretoken') return;

            if (el.type === 'file') {
                if (el.files && el.files.length) {
                    Array.prototype.forEach.call(el.files, function (f) {
                        files.push({
                            inputName: el.name,
                            fileName:  f.name,
                            type:      f.type,
                            blob:      f
                        });
                    });
                }
                return;
            }
            if (el.type === 'checkbox') {
                if (!el.checked) return;
                if (fields[el.name] === undefined) {
                    fields[el.name] = el.value;
                } else {
                    if (!Array.isArray(fields[el.name])) fields[el.name] = [fields[el.name]];
                    fields[el.name].push(el.value);
                }
                return;
            }
            if (el.type === 'radio') {
                if (el.checked) fields[el.name] = el.value;
                return;
            }
            // text, textarea, select, hidden, etc.
            if (fields[el.name] !== undefined) {
                if (!Array.isArray(fields[el.name])) fields[el.name] = [fields[el.name]];
                fields[el.name].push(el.value);
            } else {
                fields[el.name] = el.value;
            }
        });
        return { fields: fields, files: files };
    }

    function applyDraftToForm(form, draft) {
        Object.keys(draft.fields || {}).forEach(function (name) {
            var val = draft.fields[name];
            var sel = '[name="' + (window.CSS && CSS.escape ? CSS.escape(name) : name) + '"]';
            var els = form.querySelectorAll(sel);
            if (!els.length) return;
            var first = els[0];
            if (first.type === 'radio') {
                els.forEach(function (el) { el.checked = (el.value === val); });
            } else if (first.type === 'checkbox') {
                var values = Array.isArray(val) ? val : [val];
                els.forEach(function (el) { el.checked = values.indexOf(el.value) !== -1; });
            } else {
                first.value = Array.isArray(val) ? (val[0] || '') : val;
            }
            try {
                first.dispatchEvent(new Event('input',  { bubbles: true }));
                first.dispatchEvent(new Event('change', { bubbles: true }));
            } catch (e) {}
        });
    }

    // ── CSRF helper ─────────────────────────────────────────────────────────
    function getCsrfToken() {
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : '';
    }

    // ── Build FormData from a snapshot (used for sync + pending-files submit)
    function buildFormData(snap) {
        var fd = new FormData();
        var csrf = getCsrfToken();
        if (csrf) fd.append('csrfmiddlewaretoken', csrf);
        Object.keys(snap.fields || {}).forEach(function (name) {
            var val = snap.fields[name];
            if (Array.isArray(val)) {
                val.forEach(function (v) { fd.append(name, v); });
            } else {
                fd.append(name, val == null ? '' : val);
            }
        });
        (snap.files || []).forEach(function (f) {
            try { fd.append(f.inputName, f.blob, f.fileName); } catch (e) {}
        });
        return fd;
    }

    // ── UI: status pill, toasts, restore banner ────────────────────────────
    function ensureUI() {
        if (document.getElementById('clinic-offline-ui')) return;
        var host = document.createElement('div');
        host.id = 'clinic-offline-ui';
        host.innerHTML = (
            '<style>' +
            '#cof-status{position:fixed;top:74px;left:18px;background:#fff;border:1px solid #d0e4d5;' +
            'padding:6px 14px;border-radius:999px;font:12px Arial,sans-serif;color:#166534;' +
            'box-shadow:0 2px 8px rgba(0,0,0,.1);z-index:998;display:none;}' +
            '#cof-status .dot{display:inline-block;width:8px;height:8px;border-radius:50%;' +
            'margin-left:6px;background:#16a34a;vertical-align:middle;}' +
            '#cof-status.offline{color:#b45309;border-color:#fcd34d;background:#fffbeb;}' +
            '#cof-status.offline .dot{background:#b45309;}' +
            '#cof-status.show{display:inline-block;}' +
            '#cof-toast{position:fixed;bottom:22px;left:22px;background:#1a3d28;color:#fff;' +
            'padding:12px 18px;border-radius:10px;font:14px Arial,sans-serif;' +
            'box-shadow:0 8px 24px rgba(0,0,0,.25);z-index:9999;display:none;' +
            'min-width:220px;max-width:380px;line-height:1.6;}' +
            '#cof-toast.show{display:block;}' +
            '#cof-toast.warn {background:#b45309;}' +
            '#cof-toast.ok   {background:#166534;}' +
            '#cof-toast.error{background:#b91c1c;}' +
            '.cof-banner{background:#fef3c7;color:#78350f;border:1px solid #fcd34d;' +
            'border-radius:10px;padding:14px 18px;margin:0 0 18px;display:flex;' +
            'align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;' +
            'font:14px Arial,sans-serif;}' +
            '.cof-banner .cof-actions{display:flex;gap:8px;}' +
            '.cof-banner button{border:none;border-radius:8px;padding:8px 16px;font-weight:700;' +
            'cursor:pointer;font-family:inherit;font-size:13px;}' +
            '.cof-btn-primary{background:#1a6b3c;color:#fff;}' +
            '.cof-btn-primary:hover{background:#145c32;}' +
            '.cof-btn-secondary{background:#f3f4f6;color:#374151;}' +
            '.cof-btn-secondary:hover{background:#e5e7eb;}' +
            '</style>' +
            '<div id="cof-status"></div>' +
            '<div id="cof-toast"></div>'
        );
        document.body.appendChild(host);
    }

    function showToast(msg, kind, ms) {
        ensureUI();
        var t = document.getElementById('cof-toast');
        t.className = 'show ' + (kind || '');
        t.textContent = msg;
        clearTimeout(t._timer);
        t._timer = setTimeout(function () { t.className = ''; }, ms || 3500);
    }

    function setOnline(online) {
        ensureUI();
        var s = document.getElementById('cof-status');
        if (online) {
            s.classList.remove('show', 'offline');
        } else {
            s.classList.add('show', 'offline');
            s.innerHTML = '<span class="dot"></span> غير متصل — يتم الحفظ محلياً';
        }
    }

    function showRestoreBanner(form, draft, onRestore, onDiscard) {
        var banner = document.createElement('div');
        banner.className = 'cof-banner';
        var when;
        try {
            when = new Date(draft.savedAt).toLocaleString('ar-EG', {
                dateStyle: 'short', timeStyle: 'short'
            });
        } catch (e) { when = '—'; }
        var fileNote = (draft.files && draft.files.length)
            ? ' (' + draft.files.length + ' مرفق محفوظ)' : '';
        banner.innerHTML =
            '<div>💾 <b>لديك بيانات غير محفوظة</b> من جلسة سابقة بتاريخ ' + when + fileNote + '.</div>' +
            '<div class="cof-actions">' +
              '<button type="button" class="cof-btn-primary">استعادة البيانات</button>' +
              '<button type="button" class="cof-btn-secondary">تجاهل</button>' +
            '</div>';
        form.parentNode.insertBefore(banner, form);
        var btns = banner.querySelectorAll('button');
        btns[0].addEventListener('click', function () { onRestore(); banner.remove(); });
        btns[1].addEventListener('click', function () { onDiscard(); banner.remove(); });
    }

    // ── Sync queued submissions when back online ───────────────────────────
    var syncing = false;
    function syncQueue() {
        if (syncing || !navigator.onLine) return;
        syncing = true;
        listQueue().then(function (items) {
            if (!items || !items.length) { syncing = false; return; }
            showToast('🔄 جارٍ مزامنة ' + items.length + ' عنصر(عناصر)...', 'warn', 2500);
            var chain = Promise.resolve();
            items.forEach(function (item) {
                chain = chain.then(function () { return submitQueued(item); });
            });
            chain.finally(function () { syncing = false; });
        }).catch(function () { syncing = false; });
    }

    function submitQueued(item) {
        var fd = buildFormData(item);
        return fetch(item.url, {
            method: item.method || 'POST',
            body: fd,
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (resp) {
            if (resp.ok || resp.redirected) {
                return Promise.all([
                    delQueue(item.id),
                    item.formKey ? delDraft(item.formKey) : Promise.resolve()
                ]).then(function () {
                    showToast('✅ تمت مزامنة بياناتك بنجاح', 'ok', 4000);
                });
            }
            // 4xx/5xx — retain in queue for manual recovery / retry next time.
            console.warn('clinic_offline: queued submission rejected with', resp.status);
        }).catch(function (err) {
            // Network error — keep in queue, will retry on next online event.
            console.warn('clinic_offline: sync attempt failed', err);
        });
    }

    // ── Form binding ───────────────────────────────────────────────────────
    function bindForm(form) {
        if (form.dataset.cofBound) return;
        form.dataset.cofBound = '1';

        var explicitKey = form.dataset.offlineKey || form.getAttribute('data-offline');
        var key = (explicitKey && explicitKey !== 'true' && explicitKey !== '')
            ? explicitKey
            : (window.location.pathname + (form.id ? '#' + form.id : ''));
        form.dataset.offlineKey = key;

        // ── 1) Restore prompt on load ──────────────────────────────────────
        getDraft(key).then(function (draft) {
            if (!draft) return;
            // If the draft is empty (no fields and no files) skip prompting.
            var hasFields = draft.fields && Object.keys(draft.fields).length > 0;
            var hasFiles  = draft.files && draft.files.length > 0;
            if (!hasFields && !hasFiles) {
                delDraft(key);
                return;
            }
            showRestoreBanner(form, draft,
                function onRestore() {
                    applyDraftToForm(form, draft);
                    if (hasFiles) {
                        form._cofPendingFiles = draft.files;
                        showToast('📎 ' + draft.files.length +
                            ' ملف محفوظ محلياً سيُرفع عند الإرسال', 'warn', 4500);
                    }
                    showToast('✓ تمت استعادة البيانات من الجلسة السابقة', 'ok', 2500);
                },
                function onDiscard() {
                    delDraft(key).catch(function () {});
                }
            );
        }).catch(function () {});

        // ── 2) Autosave on input/change (debounced) ───────────────────────
        var saveTimer = null;
        function scheduleSave() {
            clearTimeout(saveTimer);
            saveTimer = setTimeout(doSave, SAVE_DEBOUNCE);
        }
        function doSave() {
            try {
                var snap = serializeForm(form);
                if (snap.files.length === 0 && form._cofPendingFiles) {
                    snap.files = form._cofPendingFiles;
                }
                putDraft({
                    formKey:  key,
                    pathname: window.location.pathname,
                    savedAt:  Date.now(),
                    fields:   snap.fields,
                    files:    snap.files
                }).catch(function () {});
            } catch (e) {}
        }
        form.addEventListener('input',  scheduleSave);
        form.addEventListener('change', scheduleSave);

        // Save on tab close / navigation away. Skip if the form is in the
        // middle of being submitted (we don't want to recreate a draft we
        // just deleted in the submit handler).
        function flush() {
            if (form._cofSubmitting) return;
            try { clearTimeout(saveTimer); doSave(); } catch (e) {}
        }
        window.addEventListener('beforeunload', flush);
        window.addEventListener('pagehide',     flush);

        // ── 3) Submit interception — queue if offline / has pending files ──
        form.addEventListener('submit', function (ev) {
            var hasPending = !!(form._cofPendingFiles && form._cofPendingFiles.length);
            // Stop any pending autosave from re-creating the draft after delete.
            clearTimeout(saveTimer);
            form._cofSubmitting = true;

            // Online + no carry-over files → let Django handle it normally,
            // but clean up the local draft so it doesn't reappear next visit.
            if (navigator.onLine && !hasPending) {
                delDraft(key).catch(function () {});
                return; // proceed with normal navigation
            }

            ev.preventDefault();
            var snap = serializeForm(form);
            if (snap.files.length === 0 && hasPending) snap.files = form._cofPendingFiles;
            var payload = {
                url:      form.action || window.location.href,
                method:   'POST',
                formKey:  key,
                fields:   snap.fields,
                files:    snap.files,
                queuedAt: Date.now()
            };

            if (!navigator.onLine) {
                enqueue(payload).then(function () {
                    showToast('💾 تم حفظ الإرسال محلياً — ستتم المزامنة فور عودة الاتصال',
                        'warn', 6000);
                }).catch(function () {
                    showToast('⚠️ تعذر حفظ البيانات محلياً — تحقق من إعدادات المتصفح',
                        'error', 6000);
                });
                return;
            }

            // Online with pending files (from a restored draft) — submit via fetch.
            var fd = buildFormData(snap);
            fetch(payload.url, {
                method: 'POST',
                body: fd,
                credentials: 'same-origin'
            }).then(function (resp) {
                if (resp.ok || resp.redirected) {
                    delDraft(key).catch(function () {});
                    var dest = resp.redirected ? resp.url : payload.url;
                    showToast('✅ تم الإرسال بنجاح', 'ok', 1500);
                    setTimeout(function () { window.location.href = dest; }, 400);
                } else {
                    enqueue(payload);
                    showToast('⚠️ فشل الإرسال (' + resp.status + ') — تم الحفظ محلياً',
                        'error', 6000);
                }
            }).catch(function () {
                enqueue(payload).then(function () {
                    showToast('💾 تم حفظ الإرسال محلياً — ستتم المزامنة فور عودة الاتصال',
                        'warn', 6000);
                });
            });
        });
    }

    // ── Bootstrap ──────────────────────────────────────────────────────────
    function init() {
        if (!('indexedDB' in window)) return; // graceful no-op
        ensureUI();
        if (!navigator.onLine) setOnline(false);

        window.addEventListener('online',  function () { setOnline(true);  syncQueue(); });
        window.addEventListener('offline', function () { setOnline(false); });

        document.querySelectorAll('form[data-offline]').forEach(bindForm);

        cleanupStaleDrafts();
        if (navigator.onLine) syncQueue();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
