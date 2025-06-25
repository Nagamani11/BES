from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
import random
import string
from datetime import datetime, timedelta
from django.core.validators import FileExtensionValidator
from django.contrib.auth import get_user_model
from datetime import time
from django.core.validators import MinValueValidator, MaxValueValidator
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
    WORK_TYPE_CHOICES = [
        ('Daily Helpers', 'Daily Helpers'),
        ('Cook and Clean', 'Cook and Clean'),
        ('Drivers', 'Drivers'),
        ('Play Zone', 'Play Zone'),
        ('Child and Adults Care', 'Child and Adults Care'),
        ('Pet Care', 'Pet Care'),
        ('Beauty and Salon', 'Beauty and Salon'),
        ("Mens Salon", "Men's Salon"),
        ('Electrician and AC Service', 'Electrician and AC Service'),
        ('Tutors', 'Tutors'),
        ('Plumber', 'Plumber'),
        ('Decor Services', 'Decor Services'),
        ('Nursing', 'Nursing'),
        ('Laundry', 'Laundry'),
        ('Swimming', 'Swimming'),
        ('bike_taxi', 'Bike Taxi'),
        ('auto_taxi', 'Auto Taxi'),
        ('car_taxi', 'Car Taxi'),
    ]

    EDUCATION_LEVEL_CHOICES = [
        ('High School', 'High School'),
        ('Diploma', 'Diploma'),
        ('B.Tech', 'B.Tech'),
        ('B.E', 'B.E'),
        ('B.Sc', 'B.Sc'),
        ('B.A', 'B.A'),
        ('B.Com', 'B.Com'),
        ('M.Tech', 'M.Tech'),
        ('M.Sc', 'M.Sc'),
        ('M.A', 'M.A'),
        ('M.Com', 'M.Com'),
        ('MBA', 'MBA'),
        ('PG Diploma', 'PG Diploma'),
        ('PhD', 'PhD'),
        ('Other', 'Other'),
    ]

    COUNTRY_CHOICES = [
        ('India', 'India'),
        ('United State', 'United State'),
        ('Singapore', 'Singapore'),
        ('United Kingdom', 'United Kingdom'),
        ('United Arab Emirates', 'United Arab Emirates'),
        ('Canada', 'Canada'),
        ('Australia', 'Australia'),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ('Aadhar Card', 'Aadhar Card'),
        ('PAN Card', 'PAN Card'),
        ('Degree Certificate', 'Degree Certificate'),
        ('Other Certification', 'Other Certification'),
        ('CV/Resume', 'CV/Resume'),
        ('ID Proof', 'ID Proof'),
        ('id_proof', 'ID Proof'),
        ('license', 'License'),
        ('registration', 'Registration Certificate'),
        ('vehicle_photo', 'Vehicle Photo'),
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

    # Multiple documents and certifications as JSON
    document_types = models.JSONField(default=list, blank=True, null=True)
    document_files = models.JSONField(default=list, blank=True, null=True)
    certification_types = models.JSONField(default=list, blank=True, null=True)
    certification_files = models.JSONField(default=list, blank=True, null=True)

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
    amount = models.DecimalField(max_digits=10, decimal_places=2,
                                 help_text="Amount in rupees")
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
    order = models.ForeignKey('Orders', null=True, blank=True,
                              on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


# servicesapp/models.py

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ("cash", "Cash"),
        ("card", "Card"),
        ("upi", "UPI"),
        ("wallet", "Wallet"),
    ]
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Scheduled", "Scheduled"),
        ("Completed", "Completed"),
        ("Failed", "Failed"),
    ]
    order_id = models.CharField(max_length=100, unique=True)
    customer_phone = models.CharField(max_length=15, null=True, blank=True)
    subcategory_name = models.CharField(max_length=100, null=True, blank=True)
    service_date = models.DateField(null=True, blank=True)
    full_address = models.TextField(null=True, blank=True)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2,
                                     default=0.00)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20,
                                      choices=PAYMENT_METHOD_CHOICES,
                                      default="cash")
    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_order_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True,
                                           null=True)
    razorpay_signature = models.CharField(max_length=100, blank=True,
                                          null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default="Pending")
    paid_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    booking_date = models.DateField(default=timezone.now)
    booking_time = models.CharField(
        max_length=50, default=datetime.now().strftime("%H:%M"))

    def __str__(self):
        return f"Payment #{self.id} - {self.subcategory_name} - {self.status}"

    class Meta:
        db_table = 'otp_app_payment'
        managed = False
        ordering = ["-created_at"]


class Orders(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Confirmed', 'Confirmed'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    )
    customer_phone = models.CharField(max_length=15)
    subcategory_name = models.CharField(max_length=100, blank=True)
    booking_date = models.DateField()
    booking_time = models.CharField(max_length=50)
    service_date = models.DateField()
    time = models.TimeField(default=time(9, 0))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    full_address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    worker_phone = models.CharField(max_length=20, null=True, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1,
                                 null=True, blank=True)
    feedback_submitted = models.BooleanField(default=False)
    feedback_text = models.TextField(blank=True, null=True)
    contact_disabled = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def _str_(self):
        return f"Order #{self.id} - {self.status}"

    def disable_contact(self):
        """Method to explicitly disable contact"""
        self.contact_disabled = True
        self.save()


# Rapido and Taxi Location Models


class ServicePerson(models.Model):
    VEHICLE_TYPES = [
        ('bike', 'Bike'),
        ('auto', 'Auto'),
        ('car', 'Car'),
    ]

    worker_profile = models.OneToOneField(
        'WorkerProfile',  # Assuming WorkerProfile is defined in same models.py
        on_delete=models.CASCADE,
        related_name='service_person'
    )
    vehicle_type = models.CharField(
        max_length=50,
        choices=VEHICLE_TYPES,
        help_text="Type of vehicle used for service"
    )
    is_available = models.BooleanField(
        default=True,
        help_text="Whether the service person is currently available"
    )
    current_latitude = models.FloatField(
        null=True,
        blank=True,
        help_text="Last known latitude coordinate"
    )
    current_longitude = models.FloatField(
        null=True,
        blank=True,
        help_text="Last known longitude coordinate"
    )
    rating = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0)],
        help_text="Average rating from 0 to 5"
    )
    total_rides = models.PositiveIntegerField(
        default=0,
        help_text="Total number of rides/completed services"
    )

    class Meta:
        verbose_name = "Service Person"
        verbose_name_plural = "Service People"
        ordering = ['-rating']

    def __str__(self):
        return f"{self.worker_profile.full_name} - {self.get_vehicle_type_display()}"

    @property
    def current_location(self):
        """Helper method to get location as tuple"""
        if self.current_latitude and self.current_longitude:
            return (self.current_latitude, self.current_longitude)
        return None

    def update_location(self, latitude, longitude):
        """Method to update service person's location"""
        self.current_latitude = latitude
        self.current_longitude = longitude
        self.save()


class LocationHistory(models.Model):
    service_person = models.ForeignKey(ServicePerson, on_delete=models.CASCADE)
    latitude = models.FloatField()
    longitude = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']


# getting Orders from Customer App
class Ride(models.Model):
    STATUS_CHOICES = [
        ('requested', 'Requested'),
        ('accepted', 'Accepted'),
        ('started', 'Started'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    customer_phone = models.CharField(max_length=15)
    pickup_latitude = models.FloatField()
    pickup_longitude = models.FloatField()
    pickup_address = models.TextField()

    drop_latitude = models.FloatField()
    drop_longitude = models.FloatField()
    drop_address = models.TextField()

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='requested')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    fare = models.DecimalField(max_digits=10, decimal_places=2, null=True,
                               blank=True)
    distance = models.FloatField(null=True, blank=True)
    vehicle_type = models.CharField(max_length=50,
                                    choices=ServicePerson.VEHICLE_TYPES)
    otp_code = models.CharField(max_length=10, blank=True, null=True)
    is_paid = models.BooleanField(default=False)

    class Meta:
        db_table = 'otp_app_ride'
        managed = False
        ordering = ['-created_at']

    def __str__(self):
        return f"Ride #{self.id} - {self.customer_phone}"


class Rider(models.Model):
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE)
    rider_phone = models.CharField(max_length=15, null=True, blank=True)
    customer_phone = models.CharField(max_length=15)
    pickup_address = models.TextField()
    drop_address = models.TextField()
    pickup_latitude = models.FloatField()
    pickup_longitude = models.FloatField()
    drop_latitude = models.FloatField()
    drop_longitude = models.FloatField()

    fare = models.DecimalField(max_digits=10, decimal_places=2, null=True,
                               blank=True)
    distance = models.FloatField(null=True, blank=True)
    vehicle_type = models.CharField(max_length=50)
    otp_code = models.CharField(max_length=10, blank=True, null=True)
    status = models.CharField(max_length=20)
    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
