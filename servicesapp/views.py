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
from django.db.models import Q
from .serializers import OrderSerializer
from .models import UserProfile
from django.db import transaction
from servicesapp.models import Orders
from decimal import Decimal
from django.core.cache import cache

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
    serializer = WorkerProfileSerializer(data=request.data, files=request.FILES)  # ✅ Include request.FILES
    if serializer.is_valid():
        serializer.save()
        return Response({'message': 'Worker profile created successfully.'}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# GET  and POSTAPI for FORM


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def register_worker(request):
    def format_choices(choices):
        return [{"value": c[0], "label": c[1]} for c in choices]

    if request.method == "GET":
        # Form structure response
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
            "document_type": {
                "type": "select",
                "required": True,
                "label": "Document Type",
                "choices": format_choices(WorkerProfile.DOCUMENT_TYPE_CHOICES),
            },
            "document_file": {"type": "file", "required": True, "label": "Document File"},
            "certification_file": {
                "type": "file",
                "required": False,
                "label": "Certification File"
            },
            "photo": {"type": "file", "required": True, "label": "Profile Photo"},
        }

        conditional_required_fields = {
            "certification_file": ["tutors", "nursing"]
        }

        return Response({
            "form_fields": form_fields,
            "conditional_required": conditional_required_fields
        })

    elif request.method == "POST":
        data = request.data
        work_type = data.get("work_type")

        if work_type in ["tutors", "nursing"] and not request.FILES.get("certification_file"):
            return Response({"error": "Certification file is required for tutors and nursing."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            WorkerProfile.objects.create(
                full_name=data.get("full_name"),
                phone_number=data.get("phone_number"),
                email=data.get("email"),
                work_type=work_type,
                education=data.get("education"),
                years_of_experience=data.get("years_of_experience") or None,
                experience_country=data.get("experience_country"),
                specialization=data.get("specialization"),
                document_type=data.get("document_type"),
                document_file=request.FILES.get("document_file"),
                photo=request.FILES.get("photo"),
                certification_file=request.FILES.get("certification_file")
            )
            return Response({"message": "Registration successful"}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
    action = request.data.get("action")
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

    if balance < MINIMUM_RECHARGE and (not last_notify or now - last_notify > timedelta(minutes=10)):
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

    keywords = WORK_TYPE_KEYWORDS.get(worker.work_type, [])
    if not keywords:
        return Response({"message": "No keywords mapped for this work type."}, status=204)

    # ✅ FETCH Action
    if action == "fetch":
        accepted_orders = Orders.objects.values_list("booking_date", "booking_time")
        payments = Payment.objects.filter(
            subcategory_name__in=keywords,
            status="Pending"
        ).exclude(
            Q(booking_date__in=[od[0] for od in accepted_orders]) &
            Q(booking_time__in=[od[1] for od in accepted_orders])
        ).order_by("-created_at")

        results = []
        for obj in payments:
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

    # ✅ ACCEPT Action
    elif action == "accept":
        if not booking_id:
            return Response({"error": "booking_id is required for accept"}, status=400)

        try:
            payment = Payment.objects.get(id=booking_id)
        except Payment.DoesNotExist:
            return Response({"error": "Payment not found"}, status=404)

        # check if already accepted based on date + time
        if Orders.objects.filter(
            booking_date=payment.booking_date,
            booking_time=payment.booking_time
        ).exists():
            return Response({"error": "This order is already accepted"}, status=400)

        if payment.status != "Pending":
            return Response({"error": "This order is not available for acceptance"}, status=400)

        cut_amount = payment.amount * Decimal('0.10')
        total_deduction = cut_amount

        if payment.payment_method == "cash":
            total_deduction += Decimal(str(payment.tax_amount or 0))
            if balance < total_deduction:
                return Response({"error": "Insufficient balance to accept this order."}, status=403)
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

    # ✅ CANCEL Action
    elif action == "cancel":
        if not booking_id:
            return Response({"error": "booking_id is required for cancel"}, status=400)

        try:
            payment = Payment.objects.get(id=booking_id)
        except Payment.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        order = Orders.objects.filter(
            booking_date=payment.booking_date,
            booking_time=payment.booking_time
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



@api_view(['GET'])
@permission_classes([AllowAny])
def get_accepted_orders(request):
    worker_phone = request.query_params.get('phone')
    if not worker_phone:
        return Response({"error": "Phone number is required"}, status=400)

    def normalize_phone(phone):
        return phone.replace(' ', '').replace('-', '').replace('+91', '').strip()

    normalized_phone = normalize_phone(worker_phone)
    worker = WorkerProfile.objects.filter(phone_number__endswith=normalized_phone).first()
    if not worker:
        return Response({"error": "Worker not found"}, status=404)

    work_type_key = WORK_TYPE_KEY_MAP.get(worker.work_type, worker.work_type)
    keywords = WORK_TYPE_KEYWORDS.get(work_type_key, [])

    orders = Orders.objects.filter(
        Q(status='Confirmed') | Q(status='Completed'),
        worker_phone__endswith=normalized_phone,
        subcategory_name__in=keywords
    ).order_by('-created_at')

    results = []
    for order in orders:
        results.append({
            "order_id": order.id,
            "subcategory_name": order.subcategory_name,
            "customer_phone": order.customer_phone,
            "status": order.status,
            "service_date": order.service_date.strftime("%Y-%m-%d"),
            "time": getattr(order, "time", ""),  # If you have a time field
            "total_amount": str(order.total_amount),
            "full_address": order.full_address,
            "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return Response({"data": results})
