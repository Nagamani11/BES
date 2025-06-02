from django.contrib import admin
from .models import OTP, WorkerProfile, RechargeTransaction
admin.site.register(OTP)
admin.site.register(WorkerProfile)
admin.site.register(RechargeTransaction)
