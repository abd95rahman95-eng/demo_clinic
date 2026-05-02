# Mobile App Setup — Capacitor + PWA

This document walks through turning the existing Django site into a native
iOS / Android app published on the App Store and Google Play, using Capacitor
as the wrapper.

## Architecture at a glance

```
 ┌──────────────────────────────────┐         HTTPS
 │  Native Shell  (Capacitor)       │  ─────────────────────►  Django backend
 │  ┌────────────────────────────┐  │                          (eyadatak.com)
 │  │  WebView                   │  │                            │
 │  │  loads:                    │  │                            │
 │  │   https://eyadatak.com/    │  │                            ▼
 │  │   patients/login/          │  │                       Postgres + media
 │  └────────────────────────────┘  │
 │  Native plugins (camera,         │
 │  push, file, biometric, etc.)    │
 └──────────────────────────────────┘
```

The **same Django backend** serves both web and mobile. The mobile app is a
thin native shell that loads the production website inside a webview, with
extra native APIs exposed via Capacitor's plugin bridge.

Code already wired up in this repo:

- `/manifest.webmanifest` — PWA manifest (served by `clinic_system/urls.py`)
- `/service-worker.js` — offline shell + push handling (served from root)
- `patients/static/patients/js/mobile_helpers.js` — SW registration + Capacitor bridge
- PWA meta tags in `patients/templates/patients/base.html`
- `CSRF_TRUSTED_ORIGINS` extended for `capacitor://localhost` in settings
- `/healthz` endpoint for connectivity probes

## Prerequisites

| Need                       | Why                                                |
|----------------------------|----------------------------------------------------|
| **Node.js 18+**            | Capacitor CLI runs on Node                         |
| **Android Studio**         | Build & test the Android app, deploy to Play Store |
| **macOS + Xcode 15+**      | Required for iOS builds — there is no shortcut     |
| **Apple Developer account** ($99/yr) | App Store submission                          |
| **Google Play Console** ($25 one-time) | Play Store submission                       |
| **FCM project** (free)     | Android push notifications                         |
| **APNs key** (in Apple Dev) | iOS push notifications                            |

## 1. Initialize the Capacitor project

Create the wrapper as a sibling folder to `demo_clinic/` (NOT inside it — keep
the native project separate from the Django repo).

```bash
mkdir eyadatak-mobile && cd eyadatak-mobile
npm init -y
npm install @capacitor/core @capacitor/cli
npx cap init "عيادتك" "tech.eyadatak.app" --web-dir www
```

When prompted:
- **App name:** `عيادتك` (or `Eyadatak`)
- **App ID:** `tech.eyadatak.app` (reverse-DNS — used by stores)
- **Web directory:** `www` (just a placeholder, we point at the live site)

Then create a stub `www/index.html` (Capacitor requires a webDir to exist
even if we redirect to the live site at runtime):

```bash
mkdir www
cat > www/index.html <<'HTML'
<!doctype html><meta charset="utf-8"><title>عيادتك</title>
<script>location.replace('https://eyadatak.com/patients/login/');</script>
HTML
```

## 2. Configure `capacitor.config.ts`

Replace the generated file with:

```ts
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'tech.eyadatak.app',
  appName: 'عيادتك',
  webDir: 'www',

  // Load the live production site directly. Updates ship with the Django
  // deploy — no app-store re-submission needed for content changes.
  server: {
    url: 'https://eyadatak.com',
    cleartext: false,
    androidScheme: 'https',
  },

  ios: {
    contentInset: 'always',
    limitsNavigationsToAppBoundDomains: true, // restrict webview to your domain
  },
  android: {
    allowMixedContent: false,
  },

  plugins: {
    SplashScreen: {
      launchShowDuration: 1500,
      backgroundColor: '#1a6b3c',
      androidSplashResourceName: 'splash',
      showSpinner: false,
    },
    StatusBar: {
      backgroundColor: '#1a6b3c',
      style: 'DARK',
      overlaysWebView: false,
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
};

export default config;
```

> **Trade-off note.** Pointing `server.url` at the live site is the fast
> path: deploys to the website ship to mobile users instantly. The downside
> is the native shell can't run truly offline before its first connection.
> If you later want a fully offline-capable bundle, drop `server.url` and
> ship a built copy of the site under `www/`.

## 3. Add native plugins

```bash
npm install \
  @capacitor/ios @capacitor/android \
  @capacitor/camera \
  @capacitor/push-notifications \
  @capacitor/network \
  @capacitor/preferences \
  @capacitor/splash-screen \
  @capacitor/status-bar \
  @capacitor/app
```

Optional but useful:
```bash
# Biometric login (Face ID / fingerprint) — third-party
npm install @aparajita/capacitor-biometric-auth
# Local notifications (e.g. follow-up reminders without server push)
npm install @capacitor/local-notifications
```

The web side already knows how to talk to `Camera`, `PushNotifications`, and
the back-button via `App.backButton` — see `patients/static/patients/js/
mobile_helpers.js`. As long as the plugins are installed, no extra JS work
is required.

## 4. Generate the native projects

```bash
npx cap add ios
npx cap add android
npx cap sync
```

This produces:
- `ios/` — open in **Xcode** with `npx cap open ios`
- `android/` — open in **Android Studio** with `npx cap open android`

After every `capacitor.config.ts` change OR new plugin install, re-run
`npx cap sync` to copy the changes into the native projects.

## 5. Permissions & native config

### Android (`android/app/src/main/AndroidManifest.xml`)
Add inside `<manifest>`:
```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE"/>
<uses-permission android:name="android.permission.CAMERA"/>
<uses-permission android:name="android.permission.READ_MEDIA_IMAGES"/>
<uses-feature android:name="android.hardware.camera" android:required="false"/>
```

### iOS (`ios/App/App/Info.plist`)
Add the user-facing strings explaining each permission — App Store will
reject builds without these:
```xml
<key>NSCameraUsageDescription</key>
<string>للسماح بإرفاق صور سريرية بزيارات المرضى</string>
<key>NSPhotoLibraryUsageDescription</key>
<string>لاختيار صور موجودة وإرفاقها بسجل المريض</string>
```

## 6. Push notifications

### Android (FCM)

1. Go to https://console.firebase.google.com/, create project `eyadatak-mobile`.
2. Add an Android app, package name `tech.eyadatak.app`.
3. Download `google-services.json` and drop it in `android/app/`.
4. Push tokens are sent to `/patients/api/push/register/` automatically by
   `mobile_helpers.js`. **You'll need to add this endpoint** on the Django
   side — the helper sends `{token, platform}` for each device. A minimal
   storage model + view is sufficient until you wire up FCM Admin SDK to
   actually send pushes.

### iOS (APNs)

1. In Apple Developer → Keys → Create a new key with APNs enabled.
2. Download the `.p8` file.
3. Upload it to your Firebase project (Cloud Messaging settings).
4. In Xcode → Signing & Capabilities → add **Push Notifications** and
   **Background Modes → Remote notifications**.

## 7. Build & test locally

### Android emulator
```bash
npx cap open android
# In Android Studio: Run ▶ on a Pixel emulator (API 33+).
```

### iOS simulator
```bash
npx cap open ios
# In Xcode: select an iPhone 15 simulator → ⌘R.
```

You should see the splash screen, then the live site loads inside the
webview. Camera button appears wherever there's a `<input type="file">`,
and `is-native-app` class is added to `<html>` so any future CSS can target
the native context.

## 8. App store submission

### Google Play

```bash
cd android
./gradlew bundleRelease
# Output: android/app/build/outputs/bundle/release/app-release.aab
```
Upload the `.aab` to Play Console → Internal testing → promote to
Production after at least one test cycle.

### App Store

In Xcode:
1. Select the `App` target → Signing & Capabilities → set your team.
2. Product → Archive.
3. Distribute App → App Store Connect → Upload.
4. Submit for review in https://appstoreconnect.apple.com/.

Both stores want screenshots, descriptions, privacy policy URL, and
content rating. Plan ~1–2 weeks for review on first submission.

## 9. Updating the app

Two channels:

- **Content / UI updates** (most changes) — just deploy the Django site.
  Existing app installs auto-pick up the new pages on next launch because
  the webview loads from the live URL.
- **Native updates** (new plugin, permission change, version bump) — re-run
  `npx cap sync`, build a new release, submit to stores.

## 10. Backend touchpoints (already done in this repo)

| Concern             | Where                                          | Status |
|---------------------|------------------------------------------------|--------|
| PWA manifest        | `clinic_system/urls.py` → `/manifest.webmanifest` | ✅ |
| Service worker      | `clinic_system/urls.py` → `/service-worker.js`    | ✅ |
| Health probe        | `clinic_system/urls.py` → `/healthz`              | ✅ |
| CSRF for native     | `clinic_system/settings.py` (`capacitor://localhost`) | ✅ |
| Image compression   | `patients/models.py` → `VisitAttachment.save`     | ✅ |
| Offline autosave    | `patients/static/patients/js/clinic_offline.js`   | ✅ |
| Push registration   | `/patients/api/push/register/` endpoint           | ⚠️ TODO when push is wanted |

## 11. Push registration endpoint (quick-add when ready)

```python
# patients/views.py
import json
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

@login_required(login_url='login')
@require_POST
def push_register(request):
    payload = json.loads(request.body or '{}')
    token = payload.get('token')
    platform = payload.get('platform', 'unknown')
    if not token:
        return JsonResponse({'ok': False, 'error': 'no token'}, status=400)
    # TODO: persist (user, token, platform, last_seen) in a small model
    return JsonResponse({'ok': True})
```

```python
# patients/urls.py
path('api/push/register/', views.push_register, name='push_register'),
```

This requires a `DeviceToken` model — straightforward to add when you're
ready to actually send pushes.

## 12. Cost & timeline summary

| Item                        | Cost / Time                           |
|-----------------------------|---------------------------------------|
| Apple Developer account     | $99 / year                            |
| Google Play Console         | $25 one-time                          |
| Capacitor + plugins         | Free, MIT                             |
| Firebase / FCM              | Free tier covers ~100k pushes/day     |
| Initial setup → working APK | ~1–2 days                             |
| First store submission      | ~1–2 weeks (incl. review)             |
| Maintenance                 | ~zero for content, occasional plugin / version bumps |
