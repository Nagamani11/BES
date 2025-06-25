from django.http import HttpResponseBadRequest, JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from .serializers import WorkerProfileSerializer
from datetime import timedelta
from django.utils import timezone
from rest_framework.permissions import AllowAny
import random
from twilio.rest import Client
from .models import OTP, Payment, WorkerProfile
import logging
from django.conf import settings
import razorpay
from .models import RechargeTransaction
from .models import Order
from django.contrib.auth.models import User
from .models import PasswordResetOTP
from .serializers import GenerateOTPSerializer, OrdersSerializer
from django.core.mail import send_mail
from .models import Recharge
from django.contrib.auth import authenticate
from django.db.models import Sum
from .models import Notification
import re
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from .serializers import OrderSerializer
from .models import UserProfile
from django.db import transaction
from servicesapp.models import Orders
from decimal import Decimal
from django.core.cache import cache
import json
from django.core.files.storage import default_storage
from .serializers import (
    ServicePersonSerializer,
    NearbyServicePersonSerializer
)
from .models import ServicePerson, LocationHistory
from geopy.distance import geodesic


logger = logging.getLogger(__name__)


def home(request):
    return JsonResponse({"message": "Welcome to the Home Page!"})


# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR)

# Twilio credentials
# Twilio credentials
TWILIO_ACCOUNT_SID = 'AC7abe4b38898c62f4479919dbb0844963'
TWILIO_AUTH_TOKEN = '47cf3055e834e4afc2501aaea73beb4c'
TWILIO_PHONE_NUMBER = '+19404779873'

client_generate = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# OTP Generation


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def generate_otp(request):
    print("enter")
    if request.method == 'GET':
        return Response({"message": "Send a POST request with 'phone_number' "
                        "to generate OTP."})

    phone_number = request.data.get("phone_number")
    if not phone_number:
        return Response({"error": "Phone number is required"}, status=400)

    phone = phone_number.strip().replace(' ', '')
    if not phone.startswith('+'):
        return Response({"error": "Phone number must start with country code "
                        "(e.g., +91)"}, status=400)

    try:
        # Generate a 4-digit OTP
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(4)])
        expires_at = timezone.now() + timedelta(minutes=5)
        # Save or update OTP in DB
        OTP.objects.update_or_create(
            phone_number=phone,
            defaults={'otp_code': otp_code, 'expires_at': expires_at}
        )

        # Send OTP using Twilio
        message = f"Your OTP is: {otp_code}. It will expire in 5 minutes."
        client_generate.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=phone
        )

        return Response({"message": "OTP sent successfully"}, status=200)

    except Exception as e:
        return Response({"error": "Failed to send OTP", "details": str(e)},
                        status=500)

# OTP Verification API


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    phone = request.data.get("phone_number")
    user_otp = request.data.get("otp_code")

    if not phone or not user_otp:
        return Response({"error": "Phone number and OTP are required"},
                        status=400)

    phone = phone.strip().replace(' ', '')
    if not phone.startswith('+'):
        return Response(
            {"error": "Phone number must start with country code (e.g., +91)"},
            status=400)

    try:
        otp_entry = OTP.objects.filter(phone_number=phone).first()
        if not otp_entry:
            return Response({"error": "OTP not found"}, status=400)

        if otp_entry.is_expired():
            otp_entry.delete()
            return Response({"error": "OTP expired"}, status=400)

        if otp_entry.otp_code != user_otp:
            return Response({"error": "Incorrect OTP"}, status=400)

        otp_entry.delete()

        # Check if user already exists
        user, created = UserProfile.objects.get_or_create(phone_number=phone)

        # `created` is True if user is new, False if already exists
        return Response({
            "message": "OTP verified successfully",
            "first_login": created
        }, status=200)

    except Exception as e:
        return Response({"error": "Something went wrong", "details": str(e)},
                        status=500)

# Form API for Worker Profile


@api_view(['POST'])
@permission_classes([AllowAny])
def worker_form(request):
    data = request.data.copy()

    # Parse list fields safely
    try:
        document_types = json.loads(data.get('document_types', '[]'))
        certification_types = json.loads(data.get('certification_types', '[]'))
    except json.JSONDecodeError:
        return Response({
            "error": "Invalid JSON in document_types or certification_types"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Create the worker profile
    worker = WorkerProfile.objects.create(
        full_name=data.get('full_name'),
        phone_number=data.get('phone_number'),
        email=data.get('email'),
        work_type=data.get('work_type'),
        years_of_experience=data.get('years_of_experience') or None,
        experience_country=data.get('experience_country'),
        specialization=data.get('specialization'),
        education=data.get('education'),
        document_types=document_types,
        certification_types=certification_types,
    )

    # Save photo if available
    if 'photo' in request.FILES:
        worker.photo = request.FILES['photo']

    # Save document files
    doc_files = request.FILES.getlist('document_files')
    doc_paths = []
    for doc_file in doc_files:
        path = default_storage.save(f'workers/documents/{doc_file.name}', doc_file)
        doc_paths.append(path)
    worker.document_files = doc_paths  # Already a list

    # Save certification files
    cert_files = request.FILES.getlist('certification_files')
    cert_paths = []
    for cert_file in cert_files:
        path = default_storage.save(f'workers/certifications/{cert_file.name}', cert_file)
        cert_paths.append(path)
    worker.certification_files = cert_paths  # Already a list

    # Final save
    worker.save()

    return Response({'message': 'Worker profile created successfully.'}, status=status.HTTP_200_OK)

# GET  and POSTAPI for FORM

from .models import WorkerProfile, worker_document_path, worker_certification_path, worker_photo_path
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def register_worker(request):
    def format_choices(choices):
        return [{"value": c[0], "label": c[1]} for c in choices]

    if request.method == "GET":
        form_fields = {
            "full_name": {"type": "text", "required": True, "label": "Full Name"},
            "phone_number": {"type": "text", "required": True, "label": "Phone Number"},
            "email": {"type": "email", "required": True, "label": "Email Address"},
            "work_type": {
                "type": "select",
                "required": True,
                "label": "Service Type",
                "choices": format_choices(WorkerProfile.WORK_TYPE_CHOICES),
            },
            "education": {
                "type": "select",
                "required": False,
                "label": "Education Level",
                "choices": format_choices(WorkerProfile.EDUCATION_LEVEL_CHOICES),
            },
            "years_of_experience": {
                "type": "number",
                "required": False,
                "label": "Years of Experience"
            },
            "experience_country": {
                "type": "select",
                "required": False,
                "label": "Country of Experience",
                "choices": format_choices(WorkerProfile.COUNTRY_CHOICES),
            },
            "specialization": {"type": "text", "required": False, "label": "Specialization"},

            # 👇 Updated to allow multiple selections
            "document_types": {
                "type": "multiselect",   # Indicates frontend should allow selecting multiple values
                "required": True,
                "label": "Document Types",
                "choices": format_choices(WorkerProfile.DOCUMENT_TYPE_CHOICES),
            },
            "document_files": {
                "type": "file[]",   # Indicates multiple files
                "required": True,
                "label": "Document Files"
            },
            "certification_files": {
                "type": "file[]",   # Indicates multiple files
                "required": False,
                "label": "Certification Files"
            },
            "photo": {
                "type": "file",
                "required": True,
                "label": "Profile Photo"
            },
        }

        # Conditional requirements for Tutors & Nursing
        conditional_required_fields = {
            "certification_files": ["Tutors", "Nursing"]
        }

        return Response({
            "form_fields": form_fields,
            "conditional_required": conditional_required_fields
        })


# To display all the form registration employees that be display in Admin


@api_view(['GET'])
@permission_classes([AllowAny])  # Use IsAdminUser if admin-only
def get_registered_employees(request):
    try:
        workers = WorkerProfile.objects.all().order_by('-created_at')
        serializer = WorkerProfileSerializer(workers, many=True)
        return Response({
            "status": True,
            "message": "All registered workers fetched successfully.",
            "registered_employees": serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            "status": False,
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Recharge APIs

# 1. Create a new recharge request


client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID,
                               settings.RAZORPAY_KEY_SECRET))


@api_view(['GET'])
@permission_classes([AllowAny])
def get_balance(request):
    mobile_number = request.query_params.get('mobile_number')

    if not mobile_number:
        return JsonResponse({'error': 'mobile_number is required'}, status=400)

    normalized_phone = re.sub(r'\D', '', mobile_number)
    if normalized_phone.startswith('91') and len(normalized_phone) == 12:
        normalized_phone = normalized_phone[2:]

    total_credit = Recharge.objects.filter(
        phone_number__endswith=normalized_phone,
        transaction_type='credit',
        is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0

    total_debit = Recharge.objects.filter(
        phone_number__endswith=normalized_phone,
        transaction_type='debit',
        is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0

    balance = round(total_credit - total_debit, 2)
    return JsonResponse({'balance': balance})


@api_view(['POST'])
@permission_classes([AllowAny])
def create_recharge(request):
    mobile_number = request.data.get('mobile_number')
    amount = request.data.get('amount')

    if not mobile_number or not amount:
        return JsonResponse({'error': 'mobile_number and amount are required'},
                            status=400)

    normalized_phone = re.sub(r'\D', '', mobile_number)
    if normalized_phone.startswith('91') and len(normalized_phone) == 12:
        normalized_phone = normalized_phone[2:]

    try:
        amount = int(amount)
    except ValueError:
        return JsonResponse({'error': 'Invalid amount format'}, status=400)

    # Forward this info to create_payment via frontend
    return JsonResponse({
        'message': 'Amount selected. Proceed to payment.',
        'phone_number': normalized_phone,
        'amount': amount  # in rupees
    }, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_payment(request):
    try:
        data = request.data

        # Amount in rupees (expected from frontend)
        try:
            rupee_amount = float(data['amount'])  # e.g. 100.0
        except (KeyError, ValueError):
            return JsonResponse(
                {'success': False, 'error': 'Valid amount (in rupees) is required'}, status=400)

        amount_paise = int(rupee_amount * 100)

        # Normalize phone number
        raw_phone = data.get('phone_number')
        if not raw_phone:
            return JsonResponse(
                {'success': False, 'error': 'phone_number is required'},
                status=400)

        normalized_phone = re.sub(r'\D', '', raw_phone)
        if normalized_phone.startswith('91') and len(normalized_phone) == 12:
            normalized_phone = normalized_phone[2:]
        if len(normalized_phone) != 10:
            return JsonResponse(
                {'success': False, 'error': 'Invalid phone number format'},
                status=400)

        # Validate payment method
        payment_method = data.get('payment_method', 'UPI')
        valid_methods = dict(RechargeTransaction.PAYMENT_METHOD_CHOICES)
        if payment_method not in valid_methods:
            return JsonResponse(
                {'success': False, 'error': f'Invalid payment method. Choose from: {", ".join(valid_methods.keys())}'}, status=400)

        # Optional: Get user
        user = User.objects.filter(username=normalized_phone).first()

        # 1. Create Razorpay order
        order_data = {
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {
                'user_id': str(user.id) if user else 'anonymous',
                'phone_number': normalized_phone
            }
        }
        razorpay_order = client.order.create(order_data)

        # 2. Save transaction as SUCCESS (payment is considered completed here)
        RechargeTransaction.objects.create(
            user=user,
            phone_number=normalized_phone,
            amount=rupee_amount,
            razorpay_order_id=razorpay_order['id'],
            payment_method=payment_method,
            status='Success'  # Marked as Success directly
        )

        # 3. Add to Recharge table as credit
        Recharge.objects.create(
            phone_number=normalized_phone,
            amount=rupee_amount,
            transaction_type='credit',
            is_paid=True
        )

        return JsonResponse({
            'success': True,
            'order_id': razorpay_order['id'],
            'amount_rupees': rupee_amount,
            'phone_number': normalized_phone,
            'key_id': settings.RAZORPAY_KEY_ID
        }, status=201)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def payment_callback(request):
    if request.method == 'POST':
        try:
            # Handle both JSON and form-data
            if request.content_type == 'application/json':
                data = request.data
            else:
                data = request.POST.dict()

            payment_id = data.get('razorpay_payment_id')
            order_id = data.get('razorpay_order_id')
            signature = data.get('razorpay_signature')

            if not all([payment_id, order_id, signature]):
                return JsonResponse({
                    'success': False,
                    'message': 'Missing parameters'
                }, status=400)

            # Check if we are in test mode, if so, skip signature verification
            if settings.DEBUG:  # Test mode check
                print("Skipping signature verification in test mode")
            else:
                # Verify signature in production
                params_dict = {
                    'razorpay_order_id': order_id,
                    'razorpay_payment_id': payment_id,
                    'razorpay_signature': signature
                }
                try:
                    client.utility.verify_payment_signature(params_dict)
                except razorpay.errors.SignatureVerificationError:
                    return JsonResponse({
                        'success': False,
                        'message': 'Invalid signature. Payment verification '
                        'failed.'
                    }, status=400)

            try:
                # Find the transaction based on razorpay_order_id
                transaction = RechargeTransaction.objects.get(
                    razorpay_order_id=order_id
                )

                # Update the transaction with payment details
                transaction.razorpay_payment_id = payment_id
                transaction.razorpay_signature = signature
                transaction.status = 'Completed'
                transaction.save()

                return JsonResponse({
                    'success': True,
                    'message': 'Payment verified successfully',
                    'transaction_id': transaction.id,
                    'order_id': order_id
                })
            except RechargeTransaction.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Transaction not found'
                }, status=404)

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)

    return HttpResponseBadRequest('Only POST method allowed')


# Get pending orders (notifications)

# Keyword mapping for matching orders to worker types

WORK_TYPE_KEYWORDS = {
    'daily_helpers': [
        "Welder",
        "Fitter",
        "Mason",
        "Carpenter",
        "Painter",
    ],
    'cooking_cleaning': [
        "Cook",
        "House Cleaner",
        "Dishwasher",
    ],
    'drivers': [
        "Personal Driver",
        "Long Trip Driver",
        "Rental Car Driver",
    ],
    'playzone': [
        "Kids Play Zone",
        "Box Cricket",
        "Badminton",
    ],
    'care': [
        "Childcare Provider",
        "Elder Caregiver",
        "Special Needs Care",
    ],
    'petcare': [
        "Dog Walker",
        "Pet Groomer",
        "Pet Sitter",
    ],
    'beauty_salon': [
        "Eyebrows Shaping",
        "Mehndi",
        "Makeup Services",
        "Nail Art",
        "Pedicure and Manicure",
        "Paper Painting and Decor",
    ],
    'electrician': [
        "Wiring and Installation",
        "Fan and Light Repair",
        "Switchboard Fixing",
        "Appliance Repair",
        "AC Repair",
    ],
    'tutors': [
        "School Tutor",
        "BTech Subjects",
        "Spoken English Trainer",
        "Software Courses Java",
        "Software Courses Python",
        "Software Courses Web Dev",
        "Deep Learning",
        "NLP",
        "Machine Learning",
    ],
    'plumber': [
        "Leak Repair",
        "Tap and Pipe Installation",
        "Water Tank Cleaning",
        "Drainage and Sewage",
    ],
    'decorators': [
        "Event Decor",
        "Birthday and Party Decoration",
    ],
    'nursing': [
        "Injection and IV Drip",
        "Wound Dressing",
        "Blood Pressure and Diabetes Monitoring",
        "Physiotherapy",
    ],
}


# def normalize_phone(phone):
#     return phone.replace(' ', '').replace('-', '').replace('+91', '').strip()


@api_view(['GET'])
@permission_classes([AllowAny])
def worker_orders(request):
    phone = request.GET.get('phone')
    if not phone:
        return Response({"error": "Phone number is required"}, status=400)

    normalized_phone = normalize_phone(phone)

    workers = WorkerProfile.objects.filter(
        phone_number__endswith=normalized_phone)
    if not workers.exists():
        return Response({"error": "Worker profile not found"}, status=404)

    worker = workers.first()

    keywords = WORK_TYPE_KEYWORDS.get(worker.work_type, [])
    if not keywords:
        return Response({"message": "No keywords mapped for this work type."},
                        status=204)

    keyword_query = Q()
    for keyword in keywords:
        keyword_query |= Q(subcategory_name__icontains=keyword)

    matched_orders = Order.objects.filter(
        keyword_query).order_by('-created_at')

    serializer = OrderSerializer(matched_orders, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_pending_orders(request):
    try:
        # Only pending orders
        orders = Order.objects.filter(
            status='Pending').order_by('-booking_date')

        # Define fields existing in Order model (exclude 'location_id')
        fields = [
            'id',
            'customer_phone',
            'subcategory_name',
            'booking_date',
            'service_date',
            'time',
            'total_amount',
            'status',
            'full_address',
            'created_at',
            'updated_at',
        ]

        orders_list = list(orders.values(*fields))
        return JsonResponse(orders_list, safe=False)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def accept_order(request):
    order_id = request.data.get('order_id')
    phone = request.data.get('phone')

    if not order_id or not phone:
        return Response({'error': 'order_id and phone are required'},
                        status=400)

    normalized_phone = normalize_phone(phone)

    try:
        worker = WorkerProfile.objects.get(
            phone_number__endswith=normalized_phone)
    except WorkerProfile.DoesNotExist:
        return Response({'error': 'Worker not found'}, status=404)

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order_id)
            if order.status != 'Pending':
                return Response({'error': f'Order already {order.status}'},
                                status=400)

            order.status = 'Confirmed'
            order.accepted_by = worker.phone_number
            order.updated_at = timezone.now()
            order.save()
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=404)

    return Response({'message': 'Order accepted and saved'})


@api_view(['POST'])
@permission_classes([AllowAny])
def cancel_order(request):
    order_id = request.data.get('order_id')

    if not order_id:
        return Response({'error': 'order_id is required'}, status=400)

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order_id)

            if order.status != 'Confirmed':
                return Response(
                 {'error': f'Cannot cancel an order that is {order.status}'},
                 status=400)

            cancelled_by = order.accepted_by

            # Reset order to Pending and clear accepted_by
            order.status = 'Pending'
            order.accepted_by = None
            order.updated_at = timezone.now()
            order.save()

            next_worker = WorkerProfile.objects.filter(
                work_type=order.subcategory_name
            ).exclude(phone_number=cancelled_by).first()

            if next_worker:
                order.status = 'Confirmed'
                order.accepted_by = next_worker.phone_number
                order.updated_at = timezone.now()
                order.save()

                return Response({
                    'message': f'Order cancelled and reassigned to {next_worker.full_name} ({next_worker.phone_number})'
                })
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=404)

    return Response(
        {'message': 'Order cancelled. No eligible worker found. Order remains open for others.'})


# Admin Email OTP APIs


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_login(request):
    email = request.data.get('email')
    password = request.data.get('password')

    if not email or not password:
        return Response({
            'success': False,
            'message': 'Email and password are required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'User with this email does not exist.'
        }, status=status.HTTP_404_NOT_FOUND)

    if not user.is_staff:
        # Only allow staff/admin users
        return Response({
            'success': False,
            'message': 'User is not an admin.'
        }, status=status.HTTP_403_FORBIDDEN)

    user = authenticate(username=user.username, password=password)
    if user is not None:
        # Successful login
        return Response({
            'success': True,
            'message': 'Login successful',
            'name': user.get_full_name() or user.username
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            'success': False,
            'message': 'Invalid password.'
        }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([AllowAny])
def generate_password(request):
    serializer = GenerateOTPSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'},
                            status=status.HTTP_404_NOT_FOUND)

        # Generate OTP and send to email
        otp_obj = PasswordResetOTP.generate_otp(user, email)

        # Send OTP to email
        send_mail(
            subject='Your OTP for Password Reset',
            message=f'Your OTP is {otp_obj.otp}',
            from_email='hifix.services13@gmail.com',
            recipient_list=[email],
            fail_silently=False,
        )

        logger.info(f"OTP generated: {otp_obj.otp} for email: {email}")

        return Response({
            'message': 'OTP sent successfully.',
            'otp': otp_obj.otp  # Return OTP for testing
        }, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    try:
        email = request.data.get('email')
        otp = request.data.get('otp')
        new_password = request.data.get('newPassword')

        # Ensure all required fields are provided
        if not email or not otp or not new_password:
            return Response({'message': 'All fields ('
                            'email, otp, newPassword) are required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Log incoming data for debugging (do not log passwords)
        logger.info(
            f"Request Data - Email: {email}, OTP: {otp}")

        # Validate OTP
        otp_record = PasswordResetOTP.objects.filter(
            email=email, otp=otp).first()

        # Log OTP record for debugging
        if otp_record:
            logger.info(
                f"OTP record found: {otp_record.otp} for email: {email}")
        else:
            logger.warning(
                f"OTP record not found for email: {email} and OTP: {otp}")

        if not otp_record:
            return Response({'message': 'Invalid OTP.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Check if OTP is expired or used
        if not otp_record.is_valid():
            return Response({'message': 'OTP has expired or has '
                            'already been used.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Retrieve the user and update the password
        user = User.objects.filter(email=email).first()
        if not user:
            return Response({'message': 'User not found.'},
                            status=status.HTTP_404_NOT_FOUND)

        # Update the user's password
        user.set_password(new_password)
        user.save()

        # Mark OTP as used only after successful password reset
        otp_record.is_used = True
        otp_record.save()

        return Response({'message': 'Password reset successful.'},
                        status=status.HTTP_200_OK)

    except Exception as e:
        # Catch any unexpected errors and log them
        logger.error(f"Error resetting password: {e}")
        return Response({'message': 'An unexpected error occurred. '
                        'Please try again later.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# In ADMIN all ordes access to admin
@api_view(['GET'])
@permission_classes([AllowAny])
def list_all_orders(request):
    try:
        orders = Orders.objects.all().order_by('-id')  # latest orders first
        serializer = OrdersSerializer(orders, many=True)
        return Response(serializer.data, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
# Notification API


@api_view(['GET'])
@permission_classes([AllowAny])
def notifications(request):
    phone = request.GET.get("phone")
    if not phone:
        return Response({"error": "Phone number is required"}, status=400)

    notifications = Notification.objects.filter(
        phone_number=phone).order_by('-created_at')
    data = [{
        "title": n.title,
        "message": n.message,
        "created_at": n.created_at,
        "order_id": n.order.id if n.order else None
    } for n in notifications]

    return Response({"notifications": data})

# In single API
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db.models import Q, Sum
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from decimal import Decimal
from .models import WorkerProfile, Orders, Payment, Notification, Recharge

WORK_TYPE_KEYWORDS = {
    'Daily Helpers': [
        "Welder", "Fitter", "Mason", "Carpenter", "Painter",
        "Daily Helper", "Water Tank Cleaning"
    ],
    'Cook and Clean': [
        "Cook", "House Cleaner", "Dishwasher"
    ],
    'Drivers': [
        "Personal Driver", "Long Trip Driver", "Rental Car Driver"
    ],
    'Play Zone': [
        "Kids Play Zone", "Box Cricket", "Badminton"
    ],
    'Child and Adults Care': [
        "Childcare Provider", "Elder Caregiver", "Special Needs Care"
    ],
    'Pet Care': [
        "Dog Walker", "Pet Groomer", "Pet Care Taker", "Pet Home Service"
    ],
    'Beauty and Salon': [
        "Eyebrows Shaping", "Mehndi", "Makeup Services", "Nail Art",
        "Pedicure and Manicure", "Waxing Basics", "Waxing Premium",
        "Haircut", "Head Massage", "Body Massage"
    ],
    'Mens Salon': [
        "Haircut", "Style Haircut (Creative)", "Oil Head Massage",
        "Hair Colour", "Facial (Normal)", "Body Massage (Normal)", "Shaving or Trimming"
    ],
    'Electrician and AC Service': [
        "Wiring and Installation", "Fan and Light Repair",
        "Switchboard Fixing", "Appliance Repair", "AC Repair"
    ],
    'Tutors': [
        "School Tutor", "BTech Subjects", "Spoken English Trainer",
        "Software Courses Java", "Software Courses Python"
    ],
    'Plumber': [
        "Leak Repair", "Tap and Pipe Installation", "Drainage and Sewage"
    ],
    'Decor Services': [
        "Event Decor", "Birthday and Party Decoration",
        "DJ", "Event Lighting", "Event Tent House"
    ],
    'Nursing': [
        "Injection and IV Drip", "Wound Dressing",
        "Blood Pressure and Diabetes Monitoring",
        "Orthopedic Physiotherapy", "Neurological Physiotherapy",
        "Pediatric Physiotherapy"
    ],
    'Laundry': [
        "Cloth Washing", "Iron", "Washing and Iron", "Dry Cleaning"
    ],
    'Swimming': [
        "Kids Swimming", "Trainer Swim", "Adult Swimming"
    ]
}

WORK_TYPE_KEY_MAP = {
    "beauty_salon": "Beauty and Salon",
    "mens_salon": "Mens Salon",
    "daily_helpers": "Daily Helpers",
    "cooking_cleaning": "Cook and Clean",
    "drivers": "Drivers",
    "playzone": "Play Zone",
    "care": "Child and Adults Care",
    "petcare": "Pet Care",
    "electrician": "Electrician and AC Service",
    "tutors": "Tutors",
    "plumber": "Plumber",
    "decorators": "Decor Services",
    "nursing": "Nursing",
    "laundry": "Laundry",
    "swimming": "Swimming",
    # Also allow Title Case keys for direct match
    "Beauty and Salon": "Beauty and Salon",
    "Mens Salon": "Mens Salon",
    "Daily Helpers": "Daily Helpers",
    "Cook and Clean": "Cook and Clean",
    "Drivers": "Drivers",
    "Play Zone": "Play Zone",
    "Child and Adults Care": "Child and Adults Care",
    "Pet Care": "Pet Care",
    "Electrician and AC Service": "Electrician and AC Service",
    "Tutors": "Tutors",
    "Plumber": "Plumber",
    "Decor Services": "Decor Services",
    "Nursing": "Nursing",
    "Laundry": "Laundry",
    "Swimming": "Swimming",
}

MINIMUM_RECHARGE = 50

def normalize_phone(phone):
    return phone.replace(' ', '').replace('-', '').replace('+91', '').strip()

def get_worker_balance(phone_number):
    normalized = normalize_phone(phone_number)
    credits = Recharge.objects.filter(
        phone_number__endswith=normalized,
        transaction_type='credit',
        is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0
    debits = Recharge.objects.filter(
        phone_number__endswith=normalized,
        transaction_type='debit',
        is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0
    return credits - debits

def deduct_worker_balance(phone_number, amount):
    Recharge.objects.create(
        phone_number=phone_number,
        amount=amount,
        transaction_type='debit',
        is_paid=True
    )

@api_view(['POST'])
@permission_classes([AllowAny])
def worker_job_action(request):
    phone = request.data.get("phone")
    action = request.data.get("action")  # fetch, accept, cancel
    booking_id = request.data.get("booking_id")  # This is Payment.id

    if not phone:
        return Response({"error": "Phone number is required"}, status=400)

    normalized_phone = normalize_phone(phone)
    worker = WorkerProfile.objects.filter(phone_number__endswith=normalized_phone).first()
    if not worker:
        return Response({"error": "Worker not found"}, status=404)

    balance = get_worker_balance(worker.phone_number)
    now = timezone.now()
    cache_key = f"low_balance_notify_{worker.phone_number}"
    last_notify = cache.get(cache_key)
    notify_interval = timedelta(minutes=10)

    should_notify = (
        balance < MINIMUM_RECHARGE and
        (
            not last_notify or
            now - last_notify > notify_interval
        )
    )

    if should_notify:
        Notification.objects.create(
            category="Recharge",
            title="Low Connects",
            phone_number=worker.phone_number,
            message="Connects are over. Please recharge to continue accepting orders."
        )
        cache.set(cache_key, now, timeout=60*60)

    if balance < MINIMUM_RECHARGE and action == "fetch":
        return Response({
            "error": "Low balance",
            "message": "Connects are over. Please recharge to continue accepting orders.",
            "balance": float(balance)
        }, status=403)

    work_type_key = WORK_TYPE_KEY_MAP.get(worker.work_type, worker.work_type)
    keywords = WORK_TYPE_KEYWORDS.get(work_type_key, [])
    if not keywords:
        return Response({"message": "No keywords mapped for this work type."}, status=204)

    # FETCH ACTION
    if action == "fetch":
        # Get all accepted orders as a set of tuples for fast lookup
        accepted_orders = set(Orders.objects.values_list('booking_date', 'booking_time', 'customer_phone'))
        # Only show jobs from Payment table that are not already accepted (not in Orders)
        payments = Payment.objects.filter(
            subcategory_name__in=keywords,
            status__in=["Pending", "Scheduled"]
        ).order_by("-created_at")

        results = []
        for obj in payments:
            # Exclude if already accepted (same date, time, customer)
            if (obj.booking_date, obj.booking_time, obj.customer_phone) in accepted_orders:
                continue
            results.append({
                "booking_id": obj.id,
                "subcategory_name": obj.subcategory_name,
                "customer_phone": obj.customer_phone,
                "status": obj.status,
                "service_date": obj.service_date,
                "created_at": obj.created_at,
                "total_amount": str(obj.amount),
                "full_address": obj.full_address or "",
                "service_time": obj.booking_time
            })

        return Response({"data": results, "balance": float(balance)})

    # ACCEPT ACTION
    elif action == "accept":
        if not booking_id:
            return Response({"error": "booking_id is required for accept"}, status=400)

        try:
            payment = Payment.objects.get(id=booking_id, status="Pending")
        except Payment.DoesNotExist:
            return Response({"error": "This order is already accepted or not available"}, status=400)

        if Orders.objects.filter(
            booking_date=payment.booking_date,
            booking_time=payment.booking_time,
            customer_phone=payment.customer_phone
        ).exists():
            return Response({"error": "This order is already accepted"}, status=400)

        cut_amount = payment.amount * Decimal('0.10')
        total_deduction = cut_amount

        if payment.payment_method == "cash":
            total_deduction += Decimal(str(payment.tax_amount or 0))
            if balance < total_deduction:
                return Response(
                    {"error": "Insufficient balance to accept this order."},
                    status=403)

            deduct_worker_balance(worker.phone_number, total_deduction)

        Orders.objects.create(
            customer_phone=payment.customer_phone,
            subcategory_name=payment.subcategory_name,
            booking_date=payment.booking_date,
            booking_time=payment.booking_time,
            service_date=payment.service_date or payment.booking_date,
            total_amount=payment.amount,
            status="Confirmed",
            full_address=payment.full_address or "",
            created_at=timezone.now(),
            updated_at=timezone.now(),
            worker_phone=worker.phone_number
        )

        payment.status = "Scheduled"
        payment.save()

        Notification.objects.create(
            category="Order",
            title="New Order Confirmed",
            phone_number=worker.phone_number,
            message=f"You accepted an order (Booking ID: {payment.id}) for {payment.subcategory_name} on {payment.service_date}.",
        )

        return Response({
            "message": "Order accepted",
            "booking_id": payment.id,
            "balance": float(get_worker_balance(worker.phone_number))
        })

    # CANCEL ACTION
    elif action == "cancel":
        if not booking_id:
            return Response({"error": "booking_id is required for cancel"}, status=400)

        try:
            payment = Payment.objects.get(id=booking_id)
        except Payment.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        order = Orders.objects.filter(
            booking_date=payment.booking_date,
            booking_time=payment.booking_time,
            customer_phone=payment.customer_phone
        ).first()
        if not order:
            return Response({"error": "Order not found"}, status=404)

        order.status = "Cancelled"
        order.updated_at = timezone.now()
        order.save()

        next_worker = WorkerProfile.objects.exclude(
            phone_number=worker.phone_number
        ).filter(work_type=worker.work_type).first()

        if next_worker:
            return Response({
                "message": "Order cancelled. Assign to next worker.",
                "next_worker_phone": next_worker.phone_number
            })
        else:
            return Response({"message": "Cancelled. No next worker available."})

    return Response({"error": "Invalid action"}, status=400)



@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def get_accepted_orders(request):
    # Handle phone parameter from both GET and POST
    worker_phone = request.data.get('phone') or request.query_params.get('phone')
    if not worker_phone:
        return Response({"error": "Phone number is required"}, status=400)

    def normalize_phone(phone):
        return phone.replace(" ", "").replace("-", "").replace("+91", "").strip()

    normalized_phone = normalize_phone(worker_phone)
    worker = WorkerProfile.objects.filter(phone_number__endswith=normalized_phone).first()
    if not worker:
        return Response({"error": "Worker not found"}, status=404)

    # Handle feedback submission (POST)
    if request.method == 'POST' and 'rating' in request.data:
        print("Feedback submission detected")
        order_id = request.data.get('order_id')
        if order_id:
            try:
                order = Orders.objects.get(id=order_id)
                order.rating = request.data.get('rating')
                order.feedback_text = request.data.get('feedback', '')
                order.feedback_submitted = True
                order.contact_disabled = True  # Explicitly disable contact
                order.save()
                return Response({
                    "status": "feedback_submitted",
                    "order_id": order.id,
                    "contact_disabled": True
                })
            except Orders.DoesNotExist:
                pass  # Continue to return orders

    # Determine keywords for this worker's work_type
    work_type_key = WORK_TYPE_KEY_MAP.get(worker.work_type, worker.work_type)
    keywords = WORK_TYPE_KEYWORDS.get(work_type_key, [])

    # Get accepted orders
    orders = Orders.objects.filter(
        Q(status='Confirmed') | Q(status='Completed'),
        worker_phone__endswith=normalized_phone,
        subcategory_name__in=keywords
    ).order_by('-created_at')

    results = []
    for order in orders:
        payment = Payment.objects.filter(
            booking_date=order.booking_date,
            booking_time=order.booking_time,
            customer_phone=order.customer_phone,
            subcategory_name=order.subcategory_name
        ).first()
        
        if payment:
            results.append({
                "order_id": order.id,
                "booking_id": payment.id,
                "subcategory_name": order.subcategory_name,
                "customer_phone": order.customer_phone,
                "status": order.status,
                "service_date": order.service_date.strftime("%Y-%m-%d"),
                "time": order.time.strftime("%H:%M"),
                "total_amount": str(order.total_amount),
                "full_address": order.full_address,
                "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "rating": float(order.rating) if order.rating else None,
                "feedback_submitted": order.feedback_submitted,
                "contact_disabled": order.contact_disabled,  # Explicit field
                "contact_allowed": not order.contact_disabled  # Derived field
            })

    return Response({"data": results})



# Rapido and taxi location APIs

from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status

from .models import ServicePerson, LocationHistory
from .serializers import NearbyServicePersonSerializer

geolocator = Nominatim(user_agent="prudvi.nayak@hifix.in")

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def service_persons(request):
    # --- POST: Update location ---
    if request.method == 'POST':
        service_person_id = request.data.get('id')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        if not all([service_person_id, latitude, longitude]):
            return Response({'error': 'Missing id, latitude, or longitude'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            service_person = ServicePerson.objects.get(id=service_person_id)
            service_person.current_latitude = float(latitude)
            service_person.current_longitude = float(longitude)
            service_person.save()

            # Optional: Save to location history
            LocationHistory.objects.create(
                service_person=service_person,
                latitude=latitude,
                longitude=longitude
            )

            return Response({'status': 'Location updated successfully'})
        except ServicePerson.DoesNotExist:
            return Response({'error': 'Service person not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # --- GET: Nearby service persons ---
    serializer = NearbyServicePersonSerializer(data=request.query_params)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    user_coords = (data['latitude'], data['longitude'])
    radius = data['radius']

    queryset = ServicePerson.objects.filter(is_available=True)
    if data.get('vehicle_type'):
        queryset = queryset.filter(vehicle_type=data['vehicle_type'])

    nearby_list = []

    for person in queryset:
        if person.current_latitude is not None and person.current_longitude is not None:
            try:
                person_coords = (person.current_latitude, person.current_longitude)
                distance_km = geodesic(user_coords, person_coords).km

                if distance_km <= radius:
                    try:
                        location = geolocator.reverse(person_coords, language='en')
                        address = location.address if location else "Unknown location"
                    except Exception:
                        address = "Reverse geocoding failed"

                    name = getattr(person.worker_profile, "full_name", "Unknown")

                    nearby_list.append({
                        "id": person.id,
                        "name": name,
                        "vehicle_type": person.vehicle_type,
                        "distance_km": round(distance_km, 2),
                        "location": address,
                        "rating": person.rating
                    })
            except Exception as e:
                print(f"Error processing person {person.id}: {e}")
                continue

    paginator = PageNumberPagination()
    paginated = paginator.paginate_queryset(nearby_list, request)

    if paginated is not None:
        return paginator.get_paginated_response(paginated)

    return Response(nearby_list)



# Rider Job action API

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Sum
from decimal import Decimal
from datetime import timedelta

from .models import WorkerProfile, Ride, Rider, Notification, Recharge, ServicePerson

MINIMUM_RECHARGE = 50

WORK_TYPE_KEYWORDS = ['bike', 'auto', 'car']  # used for validation

WORK_TYPE_MAP = {
    'Bike Taxi': 'bike_taxi',
    'Auto Taxi': 'auto_taxi',
    'Car Taxi': 'car_taxi',
    'bike_taxi': 'bike_taxi',
    'auto_taxi': 'auto_taxi',
    'car_taxi': 'car_taxi',
}

def normalize_phone(phone):
    return phone.replace(' ', '').replace('-', '').replace('+91', '').strip()[-10:]

def get_worker_balance(phone_number):
    normalized = normalize_phone(phone_number)
    credits = Recharge.objects.filter(
        phone_number__endswith=normalized,
        transaction_type='credit',
        is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0

    debits = Recharge.objects.filter(
        phone_number__endswith=normalized,
        transaction_type='debit',
        is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0

    return credits - debits

def deduct_worker_balance(phone_number, amount):
    Recharge.objects.create(
        phone_number=phone_number,
        amount=amount,
        transaction_type='debit',
        is_paid=True
    )

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from .models import WorkerProfile, Ride, Rider, Notification, Recharge, ServicePerson

MINIMUM_RECHARGE = 50

WORK_TYPE_KEYWORDS = ['bike', 'auto', 'car']

WORK_TYPE_MAP = {
    'Bike Taxi': 'bike_taxi',
    'Auto Taxi': 'auto_taxi',
    'Car Taxi': 'car_taxi',
    'bike_taxi': 'bike_taxi',
    'auto_taxi': 'auto_taxi',
    'car_taxi': 'car_taxi',
}

def normalize_phone(phone):
    return phone.replace(' ', '').replace('-', '').replace('+91', '').strip()[-10:]

def get_worker_balance(phone_number):
    normalized = normalize_phone(phone_number)
    credits = Recharge.objects.filter(
        phone_number__endswith=normalized,
        transaction_type='credit',
        is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0

    debits = Recharge.objects.filter(
        phone_number__endswith=normalized,
        transaction_type='debit',
        is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0

    return credits - debits

def deduct_worker_balance(phone_number, amount):
    Recharge.objects.create(
        phone_number=phone_number,
        amount=amount,
        transaction_type='debit',
        is_paid=True
    )

@api_view(['POST'])
@permission_classes([AllowAny])
def rider_job_action(request):
    phone = request.data.get("phone")
    action = request.data.get("action")
    ride_id = request.data.get("ride_id")

    if not phone:
        return Response({"error": "Phone number is required"}, status=400)

    normalized_phone = normalize_phone(phone)
    worker = WorkerProfile.objects.filter(phone_number__endswith=normalized_phone).first()

    if not worker:
        return Response({"error": "Worker not found"}, status=404)

    # Normalize work_type (handle both label and value)
    work_type_key = WORK_TYPE_MAP.get(worker.work_type)
    if not work_type_key:
        return Response({
            "error": "You are not registered as a Ride service provider (Bike/Auto/Car)",
            "hint": "Please set your work type to Bike Taxi / Auto Taxi / Car Taxi."
        }, status=403)

    vehicle_type = work_type_key.split('_')[0]  # bike, auto, car

    service_person, created = ServicePerson.objects.get_or_create(
        worker_profile=worker,
        defaults={
            "vehicle_type": vehicle_type,
            "is_available": True
        }
    )

    if service_person.vehicle_type not in WORK_TYPE_KEYWORDS:
        return Response({
            "error": "Invalid vehicle type for ride job access",
            "vehicle_type": service_person.vehicle_type
        }, status=403)

    # Balance and low balance notification
    balance = get_worker_balance(worker.phone_number)
    now = timezone.now()
    # (You can add notification logic here if needed)

    if balance < MINIMUM_RECHARGE and action == "fetch":
        return Response({
            "error": "Low balance",
            "message": "Connects are over. Please recharge to continue accepting rides.",
            "balance": float(balance)
        }, status=403)

    # FETCH Ride Jobs
    if action == "fetch":
        assigned_ride_ids = Rider.objects.values_list('ride', flat=True)
        rides = Ride.objects.filter(
            vehicle_type=service_person.vehicle_type,
            status='requested'
        ).exclude(id__in=assigned_ride_ids).order_by('-created_at')

        data = [{
            "ride_id": ride.id,
            "customer_phone": ride.customer_phone,
            "pickup_address": ride.pickup_address,
            "drop_address": ride.drop_address,
            "fare": str(ride.fare or 0),
            "distance": ride.distance,
            "created_at": ride.created_at,
            "vehicle_type": ride.vehicle_type
        } for ride in rides]

        return Response({"data": data, "balance": float(balance)})

    # ACCEPT Ride
    elif action == "accept":
        if not ride_id:
            return Response({"error": "ride_id is required for accept"}, status=400)

        try:
            ride = Ride.objects.get(id=ride_id, status="requested")
        except Ride.DoesNotExist:
            return Response({"error": "Ride not available or already accepted"}, status=404)

        if Rider.objects.filter(ride=ride).exists():
            return Response({"error": "Ride already accepted"}, status=400)

        deduction = Decimal('5.00')
        if balance < deduction:
            return Response({"error": "Insufficient balance to accept ride"}, status=403)

        deduct_worker_balance(worker.phone_number, deduction)

        ride.status = 'accepted'
        ride.updated_at = timezone.now()
        ride.save(update_fields=['status', 'updated_at'])

        Rider.objects.create(
            ride=ride,
            rider_phone=worker.phone_number,
            customer_phone=ride.customer_phone,
            pickup_address=ride.pickup_address,
            drop_address=ride.drop_address,
            pickup_latitude=ride.pickup_latitude,
            pickup_longitude=ride.pickup_longitude,
            drop_latitude=ride.drop_latitude,
            drop_longitude=ride.drop_longitude,
            fare=ride.fare,
            distance=ride.distance,
            vehicle_type=ride.vehicle_type,
            otp_code=ride.otp_code,
            status='Confirmed',
            is_paid=ride.is_paid,
            created_at=ride.created_at,
            updated_at=timezone.now()
        )

        # (Optional: send notification here)

        return Response({
            "message": "Ride accepted",
            "ride_id": ride.id,
            "balance": float(get_worker_balance(worker.phone_number))
        })

    # CANCEL Ride
    elif action == "cancel":
        if not ride_id:
            return Response({"error": "ride_id is required for cancel"}, status=400)

        try:
            ride = Ride.objects.get(id=ride_id)
        except Ride.DoesNotExist:
            return Response({"error": "Ride not found"}, status=404)

        rider = Rider.objects.filter(ride=ride).first()
        if not rider:
            return Response({"error": "Ride not yet confirmed"}, status=404)

        rider.status = "Cancelled"
        rider.updated_at = timezone.now()
        rider.save(update_fields=["status", "updated_at"])

        ride.status = "requested"
        ride.updated_at = timezone.now()
        ride.save(update_fields=["status", "updated_at"])

        # (Optional: send notification here)

        return Response({"message": "Ride cancelled and reopened for others"})

    return Response({"error": "Invalid action"}, status=400)

# To show in admin panel all rides


@api_view(['GET'])
@permission_classes([AllowAny])
def rider_orders(request):
    """
    Get all rider accepted ride orders
    """
    riders = Rider.objects.select_related('ride').all().order_by('-created_at')
    data = []
    for rider in riders:
        data.append({
            "id": rider.id,
            "ride_id": rider.ride.id if rider.ride else None,
            "rider_phone": rider.rider_phone,
            "customer_phone": rider.customer_phone,
            "pickup_address": rider.pickup_address,
            "drop_address": rider.drop_address,
            "fare": rider.fare,
            "distance": rider.distance,
            "status": rider.status,
            "created_at": rider.created_at,
            "updated_at": rider.updated_at,
        })

    return Response({"data": data}, status=status.HTTP_200_OK)
# Validate OTP for Ride Acceptance


@api_view(['POST'])
@permission_classes([AllowAny])
def validate_ride_otp(request):
    ride_id = request.data.get("ride_id")
    otp = request.data.get("otp")

    if not ride_id or not otp:
        return Response({"error": "ride_id and otp are required"}, status=400)

    try:
        ride = Ride.objects.get(id=ride_id)
    except Ride.DoesNotExist:
        return Response({"error": "Ride not found"}, status=404)

    if str(ride.otp_code) == str(otp).strip():
        return Response({"message": "OTP is valid"})
    else:
        return Response({"error": "Invalid OTP"}, status=403)



# To display accepted rides for a worker


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db.models import Q
from datetime import datetime
from .models import Rider, WorkerProfile  # import your models

@api_view(['GET'])
@permission_classes([AllowAny])
def get_accepted_rides(request):
    phone = request.query_params.get("phone")
    if not phone:
        return Response({"error": "Phone number is required"}, status=400)

    def normalize_phone(phone):
        return phone.replace(" ", "").replace("-", "").replace("+91", "").strip()

    normalized = normalize_phone(phone)

    riders = Rider.objects.filter(
        rider_phone__endswith=normalized,
        status__in=["Confirmed", "Completed"]
    ).order_by("-created_at")

    data = []
    for r in riders:
        data.append({
            "ride_id": r.ride.id,
            "status": r.status,
            "pickup_address": r.pickup_address,
            "drop_address": r.drop_address,
            "fare": str(r.fare or 0),
            "distance": r.distance,
            "vehicle_type": r.vehicle_type,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "is_paid": r.is_paid
        })

    return Response({"data": data})
