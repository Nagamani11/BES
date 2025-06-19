from rest_framework import serializers
from .models import WorkerProfile
from .models import OTP
from .models import RechargeTransaction, Order, Recharge
from .models import Notification
from .models import Orders, Payment
# OTP serializers


class OTPSerializer(serializers.ModelSerializer):
    class Meta:
        model = OTP
        fields = ['phone_number', 'otp_code', 'created_at', 'expires_at']


# Worker form serializer


class WorkerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerProfile
        fields = '__all__'

    def validate(self, data):
        work_type = data.get('work_type')
        if work_type in ['tutors', 'nursing'] and not data.get(
             'certification_file'):
            raise serializers.ValidationError({
                "certification_file": "Certification file is required for tutors and nursing."
            })
        return data

# Recharge models


class RechargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recharge
        fields = '__all__'
        read_only_fields = ['user', 'phone_number', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        phone_number = user.username  # Or wherever your phone number is stored
        validated_data['user'] = user
        validated_data['phone_number'] = phone_number
        return super().create(validated_data)

# Payment serializers


class RechargeTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RechargeTransaction
        fields = '__all__'
        read_only_fields = ['user', 'phone_number', 'status', 'created_at',
                            'updated_at']

    def create(self, validated_data):
        user = self.context['request'].user
        phone_number = user.username  # Adjust as per your User model
        validated_data['user'] = user
        validated_data['phone_number'] = phone_number
        # You can set default status as 'Pending' here if you want
        validated_data['status'] = 'Pending'
        return super().create(validated_data)

# Order APIs


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            'id', 'customer_phone', 'subcategory_name', 'booking_date',
            'service_date', 'time', 'total_amount', 'status', 'full_address',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


# Admin Email OTP serializer


class GenerateOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=4)
    newPassword = serializers.CharField(min_length=6)


# Notification Serializers


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


# serializers.py


class PaymentSerializer(serializers.ModelSerializer):
    subcategory_name = serializers.SerializerMethodField()
    service_date = serializers.SerializerMethodField()
    full_address = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id',
            'order_id',
            'customer_phone',
            'amount',
            'status',
            'payment_method',
            'booking_date',
            'booking_time',
            'subcategory_name',
            'service_date',
            'full_address',
            'created_at'
        ]

    def get_subcategory_name(self, obj):
        return obj.booking.subcategory_name if obj.booking else "N/A"

    def get_service_date(self, obj):
        return obj.booking.service_date if obj.booking else obj.booking_date

    def get_full_address(self, obj):
        return obj.booking.full_address if obj.booking else ""


class OrdersSerializer(serializers.ModelSerializer):
    class Meta:
        model = Orders
        fields = '__all__'
