from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path("signup-request/", views.signup_request_view, name="signup_request"),
    path("pricing/", views.pricing_view, name="pricing"),

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
    
    path('', views.patient_list, name='patient_list'),
    path('<int:id>/', views.patient_detail, name='patient_detail'),
]