"""
URL configuration for clinic_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.http import JsonResponse
from patients import views

# Health check used by the mobile shell to detect connectivity.
def healthz(_request):
    return JsonResponse({'ok': True, 'service': 'eyadatak'})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home_view, name='home'),
    path('patients/', include('patients.urls')),

    # ── PWA endpoints ──────────────────────────────────────────────────
    # Both files MUST be served from the root path so the service worker
    # can claim the entire origin as its scope. Templates live under
    # patients/templates/patients/ and use {% static %} tags so icon/JS
    # paths resolve correctly.
    path(
        'manifest.webmanifest',
        TemplateView.as_view(
            template_name='patients/manifest.webmanifest',
            content_type='application/manifest+json',
        ),
        name='pwa_manifest',
    ),
    path(
        'service-worker.js',
        TemplateView.as_view(
            template_name='patients/service-worker.js',
            content_type='application/javascript',
        ),
        name='pwa_service_worker',
    ),

    # ── Mobile health check ────────────────────────────────────────────
    # The Capacitor app pings this on launch + periodically to confirm
    # backend reachability.
    path('healthz', healthz, name='healthz'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) \
  + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)