/* ============================================================================
 * mobile_helpers.js
 *
 * Two responsibilities:
 *   1. Register the service worker (PWA install + offline shell).
 *   2. Bridge to Capacitor when the page is running inside the native shell:
 *        - swap the file <input> for the native camera plugin
 *        - register the device for push notifications
 *        - apply safe-area padding under iOS notches
 *        - show an "open in app" install hint to web users on mobile
 *
 * The script is loaded with `defer` from base.html on every page.
 * ========================================================================== */
(function () {
    'use strict';

    // ── 1. Service worker registration ─────────────────────────────────────
    // Skip in DEBUG / file:// / Capacitor scheme (the native shell already
    // bundles its own behaviour and a SW would interfere with the bridge).
    if ('serviceWorker' in navigator &&
        location.protocol === 'https:' || location.hostname === 'localhost') {
        window.addEventListener('load', function () {
            navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
                .then(function (reg) {
                    // Listen for updates: when a new SW is waiting we prompt
                    // to refresh so the user gets the latest UI.
                    reg.addEventListener('updatefound', function () {
                        var nw = reg.installing;
                        if (!nw) return;
                        nw.addEventListener('statechange', function () {
                            if (nw.state === 'installed' && navigator.serviceWorker.controller) {
                                // A previous SW is controlling the page → an update is ready.
                                console.info('[pwa] update available — will activate on next reload');
                            }
                        });
                    });
                })
                .catch(function (err) {
                    console.warn('[pwa] SW registration failed:', err);
                });
        });
    }

    // ── 2. Capacitor environment detection ─────────────────────────────────
    // window.Capacitor is injected by the native shell. When present the page
    // is running inside the iOS/Android app, NOT a regular browser tab.
    var Cap = window.Capacitor;
    var isNative = !!(Cap && typeof Cap.isNativePlatform === 'function' && Cap.isNativePlatform());
    var isPWA    = !isNative && (
        window.matchMedia('(display-mode: standalone)').matches ||
        window.navigator.standalone === true
    );

    // Expose tiny global so other scripts can branch behaviour. The existing
    // clinic_offline.js doesn't need this — it works fine in either context.
    window.Eyadatak = window.Eyadatak || {};
    window.Eyadatak.isNative = isNative;
    window.Eyadatak.isPWA    = isPWA;

    // Tag <html> so CSS can target each runtime.
    if (isNative) document.documentElement.classList.add('is-native-app');
    if (isPWA)    document.documentElement.classList.add('is-pwa');

    // ── 3. Native enhancements (only when running inside Capacitor) ────────
    if (isNative) {
        // a) Swap file inputs for the native camera plugin so the doctor can
        //    capture a photo without the browser's file picker. Falls back
        //    to the browser flow if @capacitor/camera isn't installed yet.
        try {
            wireUpNativeCamera();
        } catch (e) { console.warn('[mobile] camera wiring skipped:', e); }

        // b) Register for push notifications.
        try {
            wireUpPushNotifications();
        } catch (e) { console.warn('[mobile] push wiring skipped:', e); }

        // c) Tap into the hardware back button on Android — close any open
        //    dropdown/modal first, then navigate.
        try {
            wireUpHardwareBack();
        } catch (e) {}

        // d) Save-area padding for iPhones with notches.
        injectSafeAreaCss();
    }

    // ── 4. Install hint for web users on mobile (small banner) ─────────────
    // Only show on browser (not native, not already installed).
    if (!isNative && !isPWA && /Android|iPhone|iPad/i.test(navigator.userAgent)) {
        // Wait for the browser's install prompt (Chrome) or simply show a
        // one-line hint once per session for iOS Safari (no programmatic
        // prompt available there).
        showInstallHintOnce();
    }

    // ────────────────────────────────────────────────────────────────────────
    // Helpers
    // ────────────────────────────────────────────────────────────────────────

    function wireUpNativeCamera() {
        // The Camera plugin is loaded by Capacitor when @capacitor/camera is
        // installed in the native project. Until it is, this is a no-op.
        var Camera = Cap.Plugins && Cap.Plugins.Camera;
        if (!Camera) return;

        // Replace any visible file<image> input with a button that calls the
        // plugin and stuffs the result back as a File on the input.
        document.querySelectorAll('input[type="file"][accept^="image"], input[type="file"][name="image"]')
            .forEach(function (input) {
                if (input.dataset.nativeWired) return;
                input.dataset.nativeWired = '1';

                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn-action btn-edit';
                btn.style.cssText = 'margin-top:6px;display:inline-flex;gap:6px;align-items:center;';
                btn.innerHTML = '<i class="fa-solid fa-camera"></i> التقاط صورة من الكاميرا';

                btn.addEventListener('click', async function () {
                    try {
                        var photo = await Camera.getPhoto({
                            quality: 82,
                            allowEditing: false,
                            resultType: 'base64',           // CameraResultType.Base64
                            source: 'PROMPT',                // CameraSource.Prompt → user picks
                            saveToGallery: false,
                        });
                        var blob = base64ToBlob(photo.base64String, 'image/' + (photo.format || 'jpeg'));
                        var file = new File([blob], 'photo.' + (photo.format || 'jpg'),
                            { type: blob.type, lastModified: Date.now() });

                        // Drop the file into the existing <input type="file">
                        // so the rest of the form (and offline autosave) sees
                        // it exactly as a normal upload.
                        var dt = new DataTransfer();
                        dt.items.add(file);
                        input.files = dt.files;
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    } catch (e) {
                        console.warn('[mobile] camera cancelled / failed:', e);
                    }
                });

                input.parentNode.insertBefore(btn, input.nextSibling);
            });
    }

    function base64ToBlob(b64, mime) {
        var bin = atob(b64);
        var len = bin.length;
        var bytes = new Uint8Array(len);
        for (var i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
        return new Blob([bytes], { type: mime });
    }

    async function wireUpPushNotifications() {
        var PN = Cap.Plugins && Cap.Plugins.PushNotifications;
        if (!PN) return;

        try {
            var perm = await PN.checkPermissions();
            if (perm.receive !== 'granted') {
                var req = await PN.requestPermissions();
                if (req.receive !== 'granted') return;
            }
            await PN.register();

            PN.addListener('registration', function (token) {
                // Send the device token to the backend for later push delivery.
                // The endpoint is OPTIONAL — if it doesn't exist yet, skip.
                var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
                fetch('/patients/api/push/register/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrf,
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        token:    token.value,
                        platform: Cap.getPlatform ? Cap.getPlatform() : 'unknown',
                    }),
                }).catch(function () { /* endpoint may not exist yet */ });
            });

            PN.addListener('pushNotificationActionPerformed', function (action) {
                var url = action && action.notification && action.notification.data && action.notification.data.url;
                if (url) window.location.href = url;
            });
        } catch (e) {
            console.warn('[mobile] push setup error:', e);
        }
    }

    function wireUpHardwareBack() {
        var App = Cap.Plugins && Cap.Plugins.App;
        if (!App || !App.addListener) return;
        App.addListener('backButton', function (ev) {
            // Close any open dropdown / bell first.
            var openDD = document.querySelector('.nav-dropdown.open');
            var openBell = document.querySelector('.nav-bell-wrap.open');
            if (openDD)   { openDD.classList.remove('open');   return; }
            if (openBell) { openBell.classList.remove('open'); return; }
            // Otherwise navigate back, or exit the app when at the root.
            if (window.history.length > 1) {
                window.history.back();
            } else if (App.exitApp) {
                App.exitApp();
            }
        });
    }

    function injectSafeAreaCss() {
        if (document.getElementById('safe-area-css')) return;
        var s = document.createElement('style');
        s.id = 'safe-area-css';
        s.textContent =
            'html.is-native-app .navbar{padding-top:calc(15px + env(safe-area-inset-top));}' +
            'html.is-native-app .container{padding-bottom:env(safe-area-inset-bottom);}';
        document.head.appendChild(s);
    }

    function showInstallHintOnce() {
        if (sessionStorage.getItem('eyadatak_install_hint_shown')) return;
        var KEY = 'eyadatak_install_hint_shown';

        // Capture the install prompt event on Chrome-based browsers.
        var deferredPrompt = null;
        window.addEventListener('beforeinstallprompt', function (e) {
            e.preventDefault();
            deferredPrompt = e;
            buildBanner(true);
        });

        // For iOS Safari (no install API), still hint manually.
        if (/iPhone|iPad/i.test(navigator.userAgent)) {
            setTimeout(function () { buildBanner(false); }, 3500);
        }

        function buildBanner(hasPrompt) {
            if (sessionStorage.getItem(KEY)) return;
            sessionStorage.setItem(KEY, '1');

            var bar = document.createElement('div');
            bar.style.cssText = 'position:fixed;bottom:0;left:0;right:0;' +
                'background:#1a6b3c;color:white;padding:10px 16px;font:13px Arial,sans-serif;' +
                'display:flex;align-items:center;gap:10px;z-index:9998;' +
                'box-shadow:0 -4px 16px rgba(0,0,0,.18);';
            bar.innerHTML = hasPrompt
                ? '<i class="fa-solid fa-mobile-screen"></i> ثبّت تطبيق عيادتك على هاتفك للاستخدام الأسرع' +
                  '<button id="cof-install" style="margin-right:auto;background:#fff;color:#1a6b3c;border:none;border-radius:6px;padding:6px 12px;font-weight:700;font-family:inherit;cursor:pointer;">ثبّت</button>' +
                  '<button id="cof-install-no" style="background:transparent;color:white;border:none;font-family:inherit;cursor:pointer;">إغلاق</button>'
                : '<i class="fa-brands fa-app-store-ios"></i> لتثبيت التطبيق: شارك ➜ إضافة إلى الشاشة الرئيسية' +
                  '<button id="cof-install-no" style="margin-right:auto;background:transparent;color:white;border:none;font-family:inherit;cursor:pointer;">إغلاق</button>';
            document.body.appendChild(bar);

            var noBtn = bar.querySelector('#cof-install-no');
            if (noBtn) noBtn.addEventListener('click', function () { bar.remove(); });

            var yesBtn = bar.querySelector('#cof-install');
            if (yesBtn && deferredPrompt) {
                yesBtn.addEventListener('click', function () {
                    deferredPrompt.prompt();
                    deferredPrompt = null;
                    bar.remove();
                });
            }
        }
    }
})();
