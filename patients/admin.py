from django.contrib import admin
from .models import Clinic, Patient, UserProfile, Visit

admin.site.register(Clinic)
admin.site.register(UserProfile)
admin.site.register(Patient)
admin.site.register(Visit)
# Register your models here.
