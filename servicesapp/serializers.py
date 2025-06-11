from rest_framework import serializers
from .models import WorkerProfile
from .models import OTP
from .models import RechargeTransaction, Order, Recharge
from .models import Notification
from .models import Orders, Booking
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


class OrdersSerializer(serializers.ModelSerializer):
    class Meta:
        model = Orders
        fields = '__all__'


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'
