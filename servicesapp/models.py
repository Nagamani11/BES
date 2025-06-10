
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
import random
import string
from datetime import timedelta
from django.core.validators import FileExtensionValidator
from django.contrib.auth import get_user_model

User = get_user_model()


class UserProfile(models.Model):
    phone_number = models.CharField(max_length=15, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.phone_number

# OTP model for phone number verification


class OTP(models.Model):
    phone_number = models.CharField(max_length=15, unique=True)
    otp_code = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"OTP for {self.phone_number}"


# For the worker profile model form

def worker_photo_path(instance, filename):
    return f'workers/{instance.id}/photos/{filename}'


def worker_document_path(instance, filename):
    return f'workers/{instance.id}/documents/{filename}'


def worker_certification_path(instance, filename):
    return f'workers/{instance.id}/certifications/{filename}'


class WorkerProfile(models.Model):
    # Work Type Choices
    WORK_TYPE_CHOICES = [
        ('daily_helpers', 'Daily Helpers'),
        ('cooking_cleaning', 'Cooking and Cleaning'),
        ('drivers', 'Drivers'),
        ('playzone', 'PlayZone'),
        ('care', 'Child and Adults Care'),
        ('petcare', 'PetCare'),
        ('beauty_salon', 'Beauty and Salon'),
        ('electrician', 'Electrician and AC Services'),
        ('tutors', 'Tutors'),
        ('nursing', 'Nursing'),
        ('plumber', 'Plumber'),
        ('decorators', 'Function and Home Decorators'),
    ]

    # Education Level Choices
    EDUCATION_LEVEL_CHOICES = [
        ('high_school', 'High School'),
        ('diploma', 'Diploma'),
        ('btech', 'B.Tech'),
        ('be', 'B.E'),
        ('bsc', 'B.Sc'),
        ('ba', 'B.A'),
        ('bcom', 'B.Com'),
        ('mtech', 'M.Tech'),
        ('msc', 'M.Sc'),
        ('ma', 'M.A'),
        ('mcom', 'M.Com'),
        ('mba', 'MBA'),
        ('pg_diploma', 'PG Diploma'),
        ('phd', 'PhD'),
        ('other', 'Other'),
    ]

    # Country Choices
    COUNTRY_CHOICES = [
        ('india', 'India'),
        ('usa', 'USA'),
        ('singapore', 'Singapore'),
        ('uk', 'UK'),
        ('uae', 'UAE'),
        ('canada', 'Canada'),
        ('australia', 'Australia'),
    ]

    # Document Type Choices
    DOCUMENT_TYPE_CHOICES = [
        ('aadhar', 'Aadhar Card'),
        ('pan', 'PAN Card'),
        ('degree', 'Degree Certificate'),
        ('other_cert', 'Other Certification'),
        ('cv', 'CV/Resume'),
        ('id_proof', 'ID Proof'),
        ('teaching_cert', 'Teaching Certification'),
        ('medical_cert', 'Medical Certification'),
    ]

    # Personal Information
    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15)
    email = models.EmailField()

    # Work Information
    work_type = models.CharField(max_length=50, choices=WORK_TYPE_CHOICES)
    years_of_experience = models.PositiveIntegerField(blank=True, null=True)
    experience_country = models.CharField(
        max_length=50,
        choices=COUNTRY_CHOICES,
        blank=True,
        null=True
    )
    specialization = models.CharField(max_length=255, blank=True, null=True)

    # Education Information
    education = models.CharField(
        max_length=50,
        choices=EDUCATION_LEVEL_CHOICES,
        blank=True,
        null=True
    )

    # File Uploads
    photo = models.ImageField(
        upload_to=worker_photo_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])]
    )

    document_type = models.CharField(
        max_length=50,
        choices=DOCUMENT_TYPE_CHOICES,
        blank=True,
        null=True
    )
    document_file = models.FileField(
        upload_to=worker_document_path,
        validators=[FileExtensionValidator([
            'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'])],
        blank=True,
        null=True
    )

    certification_file = models.FileField(
        upload_to=worker_certification_path,
        validators=[FileExtensionValidator([
            'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'])],
        blank=True,
        null=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.full_name} ({self.get_work_type_display()})"

    @property
    def is_tutor_or_nurse(self):
        return self.work_type in ['tutors', 'nursing']

# Recharge Transaction Model


class Recharge(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    )

    phone_number = models.CharField(max_length=20, blank=True, null=True)
    amount = models.PositiveIntegerField(help_text="Amount in paise")
    transaction_type = models.CharField(max_length=10,
                                        choices=TRANSACTION_TYPE_CHOICES,
                                        default='credit')
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        phone = self.phone_number if self.phone_number else "No Phone"
        amount_in_rupees = self.amount / 100
        status = 'Paid' if self.is_paid else 'Unpaid'
        return f"{phone} - ₹{amount_in_rupees} - {self.transaction_type.capitalize()} - {status}"

# payment API


class RechargeTransaction(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('Card', 'Card'),
        ('UPI', 'UPI'),
        ('Wallet', 'Wallet'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True,
                             blank=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    razorpay_order_id = models.CharField(max_length=100)
    razorpay_payment_id = models.CharField(max_length=100, blank=True,
                                           null=True)
    razorpay_signature = models.CharField(max_length=100, blank=True,
                                          null=True)
    payment_method = models.CharField(max_length=50,
                                      choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        username = self.user.username if self.user else "Unknown User"
        phone = self.phone_number if self.phone_number else "No Phone"
        return f"{username} ({phone}) - ₹{self.amount}"


# Orders APIs
class ServiceProvider(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # Name of the service provider
    phone_number = models.CharField(max_length=15, unique=True)  # Phone number


class Order(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Confirmed', 'Confirmed'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    )

    customer_phone = models.CharField(max_length=15)
    subcategory_name = models.CharField(max_length=100, blank=True)
    booking_date = models.DateTimeField()
    service_date = models.DateField()
    time = models.TimeField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    full_address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    accepted_by = models.CharField(max_length=15, null=True, blank=True)

    class Meta:
        db_table = 'otp_app_booking'  # Using the shared table
        managed = True


# Admin Email OTP
class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=4)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"OTP for {self.email}"

    def is_valid(self):
        # Log the conditions being checked for OTP validity
        if self.is_used:
            print(f"OTP for email {self.email} has already been used.")
            return False
        if (timezone.now() - self.created_at) > timedelta(minutes=15):
            print(f"OTP for email {self.email} has expired.")
            return False
        return True

    @classmethod
    def generate_otp(cls, user, email):
        cls.objects.filter(user=user).delete()
        otp = ''.join(random.choices(string.digits, k=4))
        return cls.objects.create(user=user, otp=otp, email=email)


# Notifications Models


class Notification(models.Model):
    category = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15)
    message = models.TextField()
    order = models.ForeignKey('Orders', null=True, blank=True, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


# servicesapp/models.py

class Booking(models.Model):
    # Read-only model mapping to otp_app_booking
    customer_phone = models.CharField(max_length=15)
    subcategory_name = models.CharField(max_length=100, blank=True)
    booking_date = models.DateTimeField()
    service_date = models.DateField()
    time = models.TimeField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20)
    full_address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = 'otp_app_booking'
        managed = False


class Orders(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Confirmed', 'Confirmed'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    )

    customer_phone = models.CharField(max_length=15)
    subcategory_name = models.CharField(max_length=100, blank=True)
    booking_date = models.DateTimeField()
    service_date = models.DateField()
    time = models.TimeField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    full_address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    def __str__(self):
        return f"Orders #{self.id} - {self.status}"
