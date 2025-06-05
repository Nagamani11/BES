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
from .models import OTP
import logging
from django.conf import settings
import razorpay
from .models import RechargeTransaction
from .models import Order
from .serializers import OrderSerializer
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from .models import PasswordResetOTP
from .serializers import GenerateOTPSerializer
from django.core.mail import send_mail
from .models import Recharge
from django.contrib.auth import authenticate
from django.db.models import Sum
from .models import Notification
from .serializers import NotificationSerializer
import re
from django.db import connection


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


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    if request.method == 'GET':
        return Response({"message": "Send a POST request with 'phone_number' "
                        "and 'otp_code' to verify."})

    phone = request.data.get("phone_number")
    user_otp = request.data.get("otp_code")  # Changed 'otp' to 'otp_code'

    if not phone or not user_otp:
        return Response({"error": "Phone number and OTP are required"},
                        status=400)

    phone = phone.strip().replace(' ', '')
    if not phone.startswith('+'):
        return Response({"error": "Phone number must start with country code "
                         "(e.g., +91)"}, status=400)

    try:
        otp_entry = OTP.objects.filter(phone_number=phone).first()

        if not otp_entry:
            return Response({"error": "OTP not found"}, status=400)

        if otp_entry.is_expired():
            otp_entry.delete()
            return Response({"error": "OTP expired"}, status=400)

        if otp_entry.otp_code != user_otp:  # Fixed field name here as well
            return Response({"error": "Incorrect OTP"}, status=400)

        # Valid OTP - delete it and confirm success
        otp_entry.delete()

        return Response({"message": "OTP verified successfully"}, status=200)

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
    print("get_balance view called")  # Debug line

    mobile_number = request.query_params.get('mobile_number')  # Should include country code (e.g., +919876543210)

    if not mobile_number:
        return JsonResponse({'error': 'mobile_number is required'}, status=400)

    # Calculate total credits
    total_credit = Recharge.objects.filter(
        phone_number=mobile_number, transaction_type='credit', is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Calculate total debits
    total_debit = Recharge.objects.filter(
        phone_number=mobile_number, transaction_type='debit', is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0

    balance = total_credit - total_debit

    return JsonResponse({'balance': balance})


@api_view(['POST'])
@permission_classes([AllowAny])
def create_recharge(request):
    mobile_number = request.data.get('mobile_number')
    amount = request.data.get('amount')

    if not mobile_number:
        return JsonResponse({'error': 'mobile_number is required'}, status=400)
    if not amount:
        return JsonResponse({'error': 'amount is required'}, status=400)

    try:
        amount = int(amount)
    except ValueError:
        return JsonResponse({'error': 'Amount must be an integer'}, status=400)

    recharge = Recharge.objects.create(
        phone_number=mobile_number,
        amount=amount,
        is_paid=True
    )

    return JsonResponse({
        'message': 'Recharge successful',
        'phone_number': mobile_number,
        'amount': recharge.amount,
        'is_paid': recharge.is_paid,
        'created_at': recharge.created_at
    }, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_payment(request):
    try:
        data = request.data

        # Validate and parse amount
        try:
            amount = int(data['amount'])  # amount in paise
        except (KeyError, ValueError):
            return JsonResponse({'success': False, 'error': 'Valid amount (in paise) is required'}, status=400)

        # Get and validate phone number
        raw_phone = data.get('phone_number')
        if not raw_phone:
            return JsonResponse({'success': False, 'error': 'phone_number is required'}, status=400)

        # Normalize phone number
        normalized_phone = re.sub(r'\D', '', raw_phone)
        if normalized_phone.startswith('91') and len(normalized_phone) == 12:
            normalized_phone = normalized_phone[2:]
        if len(normalized_phone) != 10:
            return JsonResponse({'success': False, 'error': 'Invalid phone number format. Expected 10 digits.'}, status=400)

        # Validate payment method
        payment_method = data.get('payment_method', 'UPI')
        valid_methods = dict(RechargeTransaction.PAYMENT_METHOD_CHOICES)
        if payment_method not in valid_methods:
            return JsonResponse({
                'success': False,
                'error': f'Invalid payment method. Choose from: {", ".join(valid_methods.keys())}'
            }, status=400)

        # Get user if exists
        user = User.objects.filter(username=normalized_phone).first()

        # Create Razorpay order
        order_data = {
            'amount': amount,
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {
                'user_id': str(user.id) if user else 'anonymous',
                'phone_number': normalized_phone
            }
        }
        razorpay_order = client.order.create(order_data)

        # Save transaction
        RechargeTransaction.objects.create(
            user=user,
            phone_number=normalized_phone,
            amount=amount / 100,  # Convert to rupees for storage
            razorpay_order_id=razorpay_order['id'],
            payment_method=payment_method,
            status='Pending'
        )

        # Response
        return JsonResponse({
            'success': True,
            'order_id': razorpay_order['id'],
            'amount': amount,
            'currency': 'INR',
            'key_id': settings.RAZORPAY_KEY_ID,
            'payment_method': payment_method,
            'phone_number': normalized_phone
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


logger = logging.getLogger(__name__)

# Webhook endpoint


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def booking_webhook(request):
    data = request.data
    action = data.get('action')
    booking_id = data.get('booking_id')

    if not action or not booking_id:
        return Response(
            {'error': 'action and booking_id are required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        if action == 'deleted':
            Order.objects.filter(booking_reference=booking_id).delete()
            return Response({'message': 'Order deleted'})

        # Status mapping between booking and order
        status_mapping = {
            'Pending': 'pending',
            'Confirmed': 'pending',  # Treat confirmed as pending in servicesapp
            'Completed': 'completed',
            'Cancelled': 'cancelled'
        }

        order_data = {
            'booking_reference': booking_id,
            'customer_phone': data.get('customer_phone'),
            'service': data.get('subcategory_name', 'unknown'),
            'booking_date': data.get('booking_date'),
            'service_date': data.get('service_date'),
            'time': data.get('time'),
            'total_amount': data.get('total_amount'),
            'status': status_mapping.get(data.get('status'), 'pending')
        }

        # Create or update order
        order, created = Order.objects.update_or_create(
            booking_reference=booking_id,
            defaults=order_data
        )

        return Response({
            'status': 'success',
            'order_id': order.id,
            'action': 'created' if created else 'updated'
        })

    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}", exc_info=True)
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def get_pending_orders(request):
    try:
        # Only pending orders
        orders = Order.objects.filter(status='Pending').order_by('-booking_date')

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
    mobile_number = request.data.get('mobile_number')

    if not order_id or not mobile_number:
        return Response(
            {'error': 'order_id and mobile_number are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Since model does NOT have service_provider_mobile, 
        # we assume customer_phone is the phone to match
        order = Order.objects.get(id=order_id, customer_phone=mobile_number)
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found for this mobile number'},
            status=status.HTTP_404_NOT_FOUND
        )

    if order.status != 'Pending':
        return Response(
            {'error': f'Order cannot be accepted because it is {order.status}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Update status to Confirmed (instead of 'accepted' which isn't in choices)
    order.status = 'Confirmed'
    order.save()
    
    return Response(
        {'message': 'Order accepted.'},
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def cancel_order(request):
    order_id = request.data.get('order_id')
    mobile_number = request.data.get('mobile_number')

    if not order_id or not mobile_number:
        return Response(
            {'error': 'order_id and mobile_number are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        order = Order.objects.get(id=order_id, customer_phone=mobile_number)
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found for this mobile number'},
            status=status.HTTP_404_NOT_FOUND
        )

    if order.status not in ['Pending', 'Confirmed']:
        return Response(
            {'error': f'Order cannot be cancelled because it is {order.status}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    order.status = 'Cancelled'
    order.save()
    
    return Response(
        {'message': 'Order cancelled.'},
        status=status.HTTP_200_OK
    )


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

# Notification API


@api_view(['GET'])
@permission_classes([AllowAny])
def get_order_notifications(request):
    # No phone number filter
    notifications = Notification.objects.filter(
        category='order'
    ).order_by('-created_at')

    print("Notifications count:", notifications.count())
    serializer = NotificationSerializer(notifications, many=True)
    return Response(serializer.data)
