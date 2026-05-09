from django.urls import path
from . import views



urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path("signup-request/", views.signup_request_view, name="signup_request"),
    path("pricing/", views.pricing_view, name="pricing"),
    path("account/", views.account_management, name="account_management"),
    path("contact/", views.contact_us, name="contact_us"),

    path('add/', views.add_patient, name='add_patient'),
    path('edit/<int:id>/', views.edit_patient, name='edit_patient'),
    path('delete/<int:id>/', views.delete_patient, name='delete_patient'),

    path('nurse-add-visit/<int:patient_id>/', views.nurse_create_visit, name='nurse_create_visit'),
    path('doctor-pending-visits/', views.doctor_pending_visits, name='doctor_pending_visits'),
    path('waiting-list/', views.waiting_list, name='waiting_list'),
    path('doctor-complete-visit/<int:visit_id>/', views.doctor_complete_visit, name='doctor_complete_visit'),

    path('delete-visit/<int:id>/', views.delete_visit, name='delete_visit'),
    path('edit-visit/<int:id>/', views.edit_visit, name='edit_visit'),
    path('nurse-edit-visit/<int:id>/', views.nurse_edit_visit, name='nurse_edit_visit'),
    path('clear-appointment/<int:visit_id>/', views.clear_appointment, name='clear_appointment'),

    # Delete a single visit attachment (POST-only). Available to doctors
    # and nurses inside the same clinic. The view decides where to send
    # the user back based on the visit status + role; an explicit `?next=`
    # parameter overrides that.
    path('attachments/<int:attachment_id>/delete/', views.delete_visit_attachment, name='delete_visit_attachment'),

    # Notifications
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/admin/', views.notifications_admin, name='notifications_admin'),
    path('notifications/mark-all-read/', views.notifications_mark_all_read, name='notifications_mark_all_read'),

    # Live patient search (used by navbar search box)
    path('api/patients/search/', views.patient_search_api, name='patient_search_api'),

    # Dental chart — single-tooth-surface update (AJAX)
    path('api/visits/<int:visit_id>/tooth-condition/', views.update_tooth_condition, name='update_tooth_condition'),

    # AI medical assistance (Claude). Specialty-aware prompts; dentistry disabled.
    path('api/visits/<int:visit_id>/ai-assist/', views.ai_medical_assistance, name='ai_medical_assistance'),

    path('', views.patient_list, name='patient_list'),
    path('<int:id>/', views.patient_detail, name='patient_detail'),
]