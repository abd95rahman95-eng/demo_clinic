{% load static %}/* ============================================================================
 * Eyadatak service worker
 *
 * Strategy:
 *   • Static assets (CSS, JS, images, fonts)        → cache-first
 *   • Navigation requests (HTML pages)              → network-first w/ cache fallback
 *   • API + non-GET requests (POST/PUT/DELETE/AJAX) → never cached, network-only
 *   • Anthropic / external API calls                → bypassed entirely
 *
 * The IndexedDB-backed offline autosave (clinic_offline.js) handles draft
 * persistence for forms — this SW only handles network/cache behaviour.
 *
 * NOTE: This file is rendered as a Django template (the {% static %} tag
 * resolves at server time). It is served from the ROOT path so it can
 * control the entire origin (the SW scope == its serve path).
 * ========================================================================== */

const VERSION = 'eyadatak-v1';
const STATIC_CACHE  = `${VERSION}-static`;
const RUNTIME_CACHE = `${VERSION}-runtime`;

// Pre-cache the app shell so a freshly-installed PWA can boot offline.
const APP_SHELL = [
  '/patients/login/',
  '/patients/dashboard/',
  '{% static "patients/js/clinic_offline.js" %}',
  '{% static "patients/images/logo.png" %}',
  '{% static "patients/images/nav_logo.png" %}',
  '{% static "patients/images/favicon.png" %}',
  '/manifest.webmanifest',
];

// ── Install: pre-cache the shell ────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(APP_SHELL).catch((err) => {
        // Don't block install if a single asset fails — usually a stale URL.
        console.warn('[sw] partial pre-cache failure:', err);
      }))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: clear old versions ────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter((k) => !k.startsWith(VERSION))
        .map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

// ── Helpers ─────────────────────────────────────────────────────────────────
function isStaticAsset(url) {
  return /\.(css|js|png|jpg|jpeg|gif|svg|webp|woff2?|ttf|eot|ico)(\?.*)?$/i.test(url.pathname);
}

function isApiCall(url) {
  return url.pathname.startsWith('/patients/api/');
}

function isExternalAPI(url) {
  return url.hostname === 'api.anthropic.com' ||
         url.hostname === 'cdnjs.cloudflare.com';
}

// Build a minimal offline HTML page for navigation fallback. Kept inline so
// the SW always has something to show even on a cold install.
function offlineFallback() {
  return new Response(
    `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
     <title>غير متصل — عيادتك</title>
     <meta name="viewport" content="width=device-width,initial-scale=1">
     <style>
       body{font-family:Arial,sans-serif;background:#f0fdf4;margin:0;
            display:flex;align-items:center;justify-content:center;
            min-height:100vh;color:#1a3d28;padding:20px;text-align:center;}
       .card{background:white;border:1px solid #c5deca;border-radius:14px;
             padding:32px 28px;max-width:440px;box-shadow:0 8px 24px rgba(26,107,60,.1);}
       h1{margin:0 0 12px;color:#1a6b3c;}
       p{line-height:1.7;color:#475569;margin:0 0 18px;}
       button{background:#1a6b3c;color:white;border:none;border-radius:8px;
              padding:11px 22px;font-weight:700;font-family:inherit;cursor:pointer;}
     </style></head>
     <body><div class="card">
       <div style="font-size:48px;margin-bottom:10px;">📡</div>
       <h1>أنت غير متصل بالإنترنت</h1>
       <p>تعذّر الوصول إلى الخادم. سيتم حفظ ما تكتبه محلياً ومزامنته فور عودة الاتصال.</p>
       <button onclick="location.reload()">إعادة المحاولة</button>
     </div></body></html>`,
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}

// ── Fetch routing ───────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle same-origin GETs in the SW. Everything else (POST submits,
  // Anthropic calls, FA CDN) goes straight to the network so the existing
  // offline-queue mechanism in clinic_offline.js can handle it correctly.
  if (req.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;
  if (isExternalAPI(url)) return;

  // Never cache the API or admin — always go to network.
  if (isApiCall(url) || url.pathname.startsWith('/admin/') ||
      url.pathname.startsWith('/media/')) {
    return;
  }

  // Static assets: cache-first.
  if (isStaticAsset(url) || url.pathname === '/manifest.webmanifest') {
    event.respondWith(
      caches.match(req).then((hit) => {
        if (hit) return hit;
        return fetch(req).then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(STATIC_CACHE).then((c) => c.put(req, clone));
          }
          return res;
        });
      })
    );
    return;
  }

  // Navigation requests (HTML pages): network-first, fall back to cache,
  // then to the inline offline page.
  if (req.mode === 'navigate' ||
      (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(RUNTIME_CACHE).then((c) => c.put(req, clone));
          }
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || offlineFallback()))
    );
    return;
  }
});

// ── Push notifications ──────────────────────────────────────────────────────
// Display a basic notification when the server pushes one. The actual
// click-through routing lives in 'notificationclick'.
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {}
  const title = data.title || 'إشعار من عيادتك';
  const options = {
    body:  data.body  || '',
    icon:  '{% static "patients/images/logo.png" %}',
    badge: '{% static "patients/images/favicon.png" %}',
    data:  { url: data.url || '/patients/dashboard/' },
    dir:   'rtl',
    lang:  'ar',
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/patients/dashboard/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        for (const c of clients) {
          if (c.url.includes(url) && 'focus' in c) return c.focus();
        }
        return self.clients.openWindow(url);
      })
  );
});
