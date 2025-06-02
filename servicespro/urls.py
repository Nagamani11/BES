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
    path('worker_form/', views.worker_form, name='worker_form'),
    # Recharge APIs
    path('get_balance/', views.get_balance, name='get_balance'),
    path('create_recharge/', views.create_recharge, name='create_recharge'),
    # payment APIs
    path('create_payment/', views.create_payment, name='create_payment'),
    path('payment_callback/', views.payment_callback, name='payment_callback'),
    # Order APIs
    path('get_pending_orders/<int:provider_id>/', views.get_pending_orders,
         name='get_pending_orders'),
    path('accept_order/<int:order_id>/', views.accept_order,
         name='accept_order'),
    path('cancel_order/<int:order_id>/', views.cancel_order,
         name='cancel_order'),
    # Admin Email OTP
    path('generate_password/', views.generate_password,
         name='generate_password'),
    path('reset_password/', views.reset_password, name='reset_password'),
    path('admin_login/', views.admin_login, name='admin_login'),
    path('get_order_notifications/', views.get_order_notifications,
         name='get_order_notifications'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
