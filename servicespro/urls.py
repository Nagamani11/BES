"""
URL configuration for servicespro project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
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
from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from servicesapp import views


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    # generate & verify otp
    path('generate_otp/', views.generate_otp, name='generate_otp'),
    path('verify_otp/', views.verify_otp, name='verify_otp'),
    # Form API
    path('worker_form/', views.worker_form, name='worker_form'),
    # Recharge APIs
    path('get_balance/', views.get_balance, name='get_balance'),
    path('create_recharge/', views.create_recharge, name='create_recharge'),
    # payment APIs
    path('create_payment/', views.create_payment, name='create_payment'),
    path('payment_callback/', views.payment_callback, name='payment_callback'),
    # Order APIs
    path('worker_orders/', views.worker_orders, name='worker_orders'),
    path('get_pending_orders/', views.get_pending_orders,
         name='get_pending_orders'),
    path('accept_order/', views.accept_order,
         name='accept_order'),
    path('cancel_order/', views.cancel_order,
         name='cancel_order'),
    # Admin Email OTP
    path('generate_password/', views.generate_password,
         name='generate_password'),
    path('reset_password/', views.reset_password, name='reset_password'),
    path('admin_login/', views.admin_login, name='admin_login'),
    path('notifications/', views.notifications,
         name='notifications'),
    path('copy_booking_order/', views.copy_booking_order,
         name='copy_booking_order'),
    path('workers_orders/', views.workers_orders, name='workers_orders'),
    path('worker_job_action/', views.worker_job_action,
         name='worker_job_action'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
