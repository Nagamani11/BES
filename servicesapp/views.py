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
from .models import OTP, WorkerProfile
import logging
from django.conf import settings
import razorpay
from .models import RechargeTransaction
from .models import Order
from django.contrib.auth.models import User
from .models import PasswordResetOTP
from .serializers import GenerateOTPSerializer
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
from servicesapp.models import Booking, Orders
from django.utils.timezone import now


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


@api_view(['POST'])
@permission_classes([AllowAny])
def worker_form(request):
    serializer = WorkerProfileSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({'message': 'Worker profile created successfully.'},
                        status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
    orders = Orders.objects.all().order_by('-id')  # latest first
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)

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


# servicesapp/views.py


@api_view(['POST'])
@permission_classes([AllowAny])
def copy_booking_order(request):
    booking_id = request.data.get("booking_id")

    try:
        booking = Booking.objects.get(id=booking_id)
        order = Orders.objects.create(
            customer_phone=booking.customer_phone,
            subcategory_name=booking.subcategory_name,
            booking_date=booking.booking_date,
            service_date=booking.service_date,
            time=booking.time,
            total_amount=booking.total_amount,
            status=booking.status,
            full_address=booking.full_address,
            created_at=booking.created_at,
            updated_at=booking.updated_at,
        )
        return Response({"message": "Order created successfully",
                         "order_id": order.id})
    except Booking.DoesNotExist:
        return Response({"error": "Booking not found"}, status=404)


# views.py


WORK_TYPE_KEYWORDS = {
    'daily_helpers': ["Welder", "Fitter", "Mason", "Carpenter", "Painter"],
    'cooking_cleaning': ["Cook", "House Cleaner", "Dishwasher"],
    'drivers': ["Personal Driver", "Long Trip Driver", "Rental Car Driver"],
    'playzone': ["Kids Play Zone", "Box Cricket", "Badminton"],
    'care': ["Childcare Provider", "Elder Caregiver", "Special Needs Care"],
    'petcare': ["Dog Walker", "Pet Groomer", "Pet Sitter"],
    'beauty_salon': ["Eyebrows Shaping", "Mehndi", "Makeup Services",
                     "Nail Art", "Pedicure and Manicure",
                     "Paper Painting and Decor"],
    'electrician': ["Wiring and Installation", "Fan and Light Repair",
                    "Switchboard Fixing", "Appliance Repair", "AC Repair"],
    'tutors': ["School Tutor", "BTech Subjects", "Spoken English Trainer",
               "Software Courses Java", "Software Courses Python",
               "Software Courses Web Dev", "Deep Learning", "NLP",
               "Machine Learning"],
    'plumber': ["Leak Repair", "Tap and Pipe Installation",
                "Water Tank Cleaning", "Drainage and Sewage"],
    'decorators': ["Event Decor", "Birthday and Party Decoration"],
    'nursing': ["Injection and IV Drip", "Wound Dressing",
                "Blood Pressure and Diabetes Monitoring", "Physiotherapy"],
}


def normalize_phone(phone):
    return phone.replace(' ', '').replace('-', '').replace('+91', '').strip()


@api_view(['GET'])
@permission_classes([AllowAny])
def workers_orders(request):
    phone = request.GET.get('phone')
    if not phone:
        return Response({"error": "Phone number is required"}, status=400)

    normalized_phone = normalize_phone(phone)

    workers = WorkerProfile.objects.filter(
        phone_number__endswith=normalized_phone)
    if not workers.exists():
        return Response({"error": "Worker profile not found"}, status=404)

    worker = workers.first()

    if not worker.work_type:
        return Response({"error": "Worker work type not defined"}, status=400)

    keywords = WORK_TYPE_KEYWORDS.get(worker.work_type, [])
    if not keywords:
        return Response({"message": "No keywords mapped for this work type."},
                        status=204)

    # Create filter
    keyword_query = Q()
    for keyword in keywords:
        if keyword:
            keyword_query |= Q(subcategory_name__icontains=keyword)

    bookings = Booking.objects.filter(keyword_query)
    orders = Orders.objects.filter(keyword_query)

    combined = list(bookings) + list(orders)
    combined.sort(key=lambda obj: getattr
                  (obj, 'created_at', now()), reverse=True)

    results = []
    for obj in combined:
        results.append({
            "source": "booking" if isinstance(obj, Booking) else "order",
            "subcategory_name": obj.subcategory_name,
            "customer_phone": obj.customer_phone,
            "status": obj.status,
            "service_date": obj.service_date,
            "created_at": obj.created_at,
            "total_amount": str(obj.total_amount),
        })

    return Response(results)

# In single API


WORK_TYPE_KEYWORDS = {
    'daily_helpers': [  # Category ID 1
        "Welder", "Fitter", "Mason", "Carpenter", "Painter",
        "Daily Helper", "Water Tank Cleaning"
    ],
    'cooking_cleaning': [  # Category ID 2
        "Cook", "House Cleaner", "Dishwasher"
    ],
    'drivers': [  # Category ID 3
        "Personal Driver", "Long Trip Driver", "Rental Car Driver"
    ],
    'playzone': [  # Category ID 4
        "Kids Play Zone", "Box Cricket", "Badminton"
    ],
    'care': [  # Category ID 5
        "Childcare Provider", "Elder Caregiver", "Special Care"
    ],
    'petcare': [  # Category ID 6
         "Pet Groomer", "Pet Care Taker", "Pet Home Service"
    ],
    'beauty_salon': [  # Category ID 7
        "Eyebrows Shaping", "Mehndi", "Makeup Services", "Nail Art",
        "Pedicure and Manicure", "Waxing Basics", "Waxing Premium",
        "Haircut", "Head Massage", "Body Massage"
    ],
    'electrician': [  # Category ID 8
        "Wiring and Installation", "Fan and Light Repair",
        "Switchboard Fixing", "Appliance Repair", "AC Repair"
    ],
    'tutors': [  # Category ID 9
        "School Tutor", "BTech Subjects", "Spoken English Trainer",
        "Software Courses Java", "Software Courses Python"
    ],
    'plumber': [  # Category ID 10
        "Leak Repair", "Tap and Pipe Installation", "Drainage and Sewage"
    ],
    'decorators': [  # Category ID 11
        "Event Decor", "Birthday and Party Decoration",
        "DJ", "Event Lighting", "Event Tent House"
    ],
    'nursing': [  # Category ID 12
        "Injection and IV Drip", "Wound Dressing",
        "Blood Pressure and Diabetes Monitoring",
        "Orthopedic Physiotherapy", "Neurological Physiotherapy",
        "Cardiopulmonary Physiotherapy", "Pediatric Physiotherapy"
    ],
    'laundry': [  # Category ID 13
        "Cloth Washing", "Iron", "Washing and Iron", "Dry Cleaning"
    ],
    'swimming': [  # Category ID 14
        "Kids Swimming", "Trainer Swim", "Adult Swimming"
    ]
}


def normalize_phone(phone):
    return phone.replace(' ', '').replace('-', '').replace('+91', '').strip()


@api_view(['POST'])
@permission_classes([AllowAny])
def worker_job_action(request):
    phone = request.data.get("phone")
    action = request.data.get("action")  # fetch, accept, cancel
    booking_id = request.data.get("booking_id")
    order_id = request.data.get("order_id")

    if not phone:
        return Response({"error": "Phone number is required"}, status=400)

    normalized_phone = normalize_phone(phone)
    worker = WorkerProfile.objects.filter(
        phone_number__endswith=normalized_phone).first()
    if not worker:
        return Response({"error": "Worker not found"}, status=404)

    keywords = WORK_TYPE_KEYWORDS.get(worker.work_type, [])
    if not keywords:
        return Response({"message": "No keywords mapped for this work type."},
                        status=204)

    keyword_query = Q()
    for keyword in keywords:
        keyword_query |= Q(subcategory_name__icontains=keyword)

    # Action 1: Fetch eligible bookings
    if action == "fetch":
        bookings = Booking.objects.filter(keyword_query).exclude(
            booking_date__in=Orders.objects.values_list('booking_date',
                                                        flat=True)
        ).order_by('created_at')

        results = []
        for obj in bookings:
            results.append({
                "booking_id": obj.id,
                "subcategory_name": obj.subcategory_name,
                "customer_phone": obj.customer_phone,
                "status": obj.status,
                "service_date": obj.service_date,
                "created_at": obj.created_at,
                "total_amount": str(obj.total_amount),
                "full_address": obj.full_address
            })
        return Response({"data": results})

    # Action 2: Accept booking and copy to Orders
    elif action == "accept":
        if not booking_id:
            return Response({"error": "booking_id is required for accept"},
                            status=400)
        try:
            booking = Booking.objects.get(id=booking_id)

            if Orders.objects.filter(
                  booking_date=booking.booking_date).exists():
                return Response({"error": "This booking is already accepted"},
                                status=400)

            order = Orders.objects.create(
                customer_phone=booking.customer_phone,
                subcategory_name=booking.subcategory_name,
                booking_date=booking.booking_date,
                service_date=booking.service_date,
                time=booking.time,
                total_amount=booking.total_amount,
                status="Confirmed",
                full_address=booking.full_address,
                created_at=now(),
                updated_at=now(),
            )

            #  Create Notification for Worker
            Notification.objects.create(
                category="Order",
                title="New Order Confirmed",
                phone_number=worker.phone_number,
                message=f"You accepted an order for {booking.subcategory_name} on {booking.service_date}.",
                order=order
            )

            return Response(
                {"message": "Order accepted", "order_id": order.id})
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=404)

    # Action 3: Cancel and assign to next eligible worker
    elif action == "cancel":
        if not order_id:
            return Response({"error": "order_id is required for cancel"},
                            status=400)
        try:
            order = Orders.objects.get(id=order_id)
            order.status = "Cancelled"
            order.save()

            # Find next eligible worker
            next_worker = WorkerProfile.objects.exclude(
                phone_number=worker.phone_number).filter(
                    work_type=worker.work_type).first()
            if next_worker:
                return Response({
                    "message": "Order cancelled. Assign to next worker.",
                    "next_worker_phone": next_worker.phone_number
                })
            else:
                return Response(
                    {"message": "Cancelled. No next worker available."})
        except Orders.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

    return Response({"error": "Invalid action"}, status=400)


# to display in orders
@api_view(['GET'])
@permission_classes([AllowAny])
def get_accepted_orders(request):
    worker_phone = request.query_params.get('phone')
    if not worker_phone:
        return Response({"error": "Phone number is required"}, status=400)
    try:
        # Get orders that are either Confirmed or Completed
        orders = Orders.objects.filter(
            Q(status='Confirmed') | Q(status='Completed')
        ).order_by('-created_at')
        results = []
        for order in orders:
            results.append({
                "order_id": order.id,
                "subcategory_name": order.subcategory_name,
                "customer_phone": order.customer_phone,
                "status": order.status,
                "service_date": order.service_date.strftime("%Y-%m-%d"),
                "time": order.time.strftime("%H:%M"),
                "total_amount": str(order.total_amount),
                "full_address": order.full_address,
                "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            })
        return Response({"data": results})
    except Exception as e:
        return Response({"error": str(e)}, status=500)
