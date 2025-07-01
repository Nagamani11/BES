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
    path('register_worker/', views.register_worker, name='register_worker'),
    path('get_registered_employees/', views.get_registered_employees,
         name='get_registered_employees'),
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
    path('list_all_orders/', views.list_all_orders, name='list_all_orders'),
    path('notifications/', views.notifications,
         name='notifications'),
    path('save_push_token/', views.save_push_token,
         name='save_push_token'),
    path('worker_job_action/', views.worker_job_action,
         name='worker_job_action'),
    path('get_accepted_orders/', views.get_accepted_orders,
         name='get_accepted_orders'),
    # Rapido and Taxi location APIs
    path('service_persons/', views.service_persons, name='service_persons'),
    path('service_persons/<int:pk>/', views.service_persons,
         name='service_persons'),
    path('rider_job_action/', views.rider_job_action,
         name='rider_job_action'),
    path('rider_orders/', views.rider_orders,
         name='rider_orders'),
    path('validate_ride_otp/', views.validate_ride_otp,
         name='validate_ride_otp'),
    path('get_accepted_rides/', views.get_accepted_rides,
         name='get_accepted_rides'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
