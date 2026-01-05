from rest_framework import serializers
from .models import Booking, Passenger
from flights.serializers import FlightResultSerializer


class PassengerSerializer(serializers.ModelSerializer):
    firstName = serializers.CharField(source='first_name')
    lastName = serializers.CharField(source='last_name')
    dateOfBirth = serializers.DateField(source='date_of_birth')
    passportNumber = serializers.CharField(source='passport_number', required=False, allow_null=True)
    
    class Meta:
        model = Passenger
        fields = [
            'firstName', 'lastName', 'dateOfBirth', 'email', 'phone',
            'passportNumber', 'nin', 'bvn'
        ]


class BookingSerializer(serializers.ModelSerializer):
    bookingId = serializers.CharField(source='booking_id', read_only=True)
    tripType = serializers.CharField(source='trip_type')
    paymentMethod = serializers.CharField(source='payment_method')
    paymentReference = serializers.CharField(source='payment_reference', read_only=True, allow_null=True)
    paymentStatus = serializers.CharField(source='payment_status', read_only=True)
    pnrStatus = serializers.CharField(source='pnr_status', read_only=True, allow_null=True)
    reissueAmount = serializers.DecimalField(source='reissue_amount', max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    reissueStatus = serializers.CharField(source='reissue_status', read_only=True, allow_null=True)
    bookingDate = serializers.DateTimeField(source='booking_date', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    passengers = PassengerSerializer(many=True, read_only=True)
    flightResult = FlightResultSerializer(read_only=True)
    
    # For list view
    passenger = serializers.SerializerMethodField()
    dob = serializers.SerializerMethodField()
    airline = serializers.SerializerMethodField()
    origin = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()
    departureTime = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id', 'bookingId', 'tripType', 'status', 'amount', 'paymentMethod',
            'paymentReference', 'paymentStatus', 'pnr', 'pnrStatus', 'reissueAmount', 
            'reissueStatus', 'bookingDate', 'createdAt', 'updatedAt', 'flightResult', 
            'passengers',
            # List view fields
            'passenger', 'dob', 'airline', 'origin', 'destination',
            'departureTime', 'date', 'time'
        ]
        read_only_fields = ['bookingId', 'bookingDate', 'createdAt', 'updatedAt']
    
    def get_passenger(self, obj):
        """Get first passenger name for list view"""
        first_passenger = obj.passengers.first()
        if first_passenger:
            return f"{first_passenger.first_name} {first_passenger.last_name}"
        return ""
    
    def get_dob(self, obj):
        """Get first passenger DOB for list view"""
        first_passenger = obj.passengers.first()
        return first_passenger.date_of_birth if first_passenger else None
    
    def get_airline(self, obj):
        """Get airline name for list view"""
        return obj.flight_result.airline_name
    
    def get_origin(self, obj):
        """Get departure code for list view"""
        return obj.flight_result.departure_code
    
    def get_destination(self, obj):
        """Get arrival code for list view"""
        return obj.flight_result.arrival_code
    
    def get_departureTime(self, obj):
        """Get departure time for list view"""
        return obj.flight_result.departure_time
    
    def get_date(self, obj):
        """Get departure date for list view"""
        return obj.flight_result.departure_time.date()
    
    def get_time(self, obj):
        """Get departure time for list view"""
        return obj.flight_result.departure_time.time()


class BookingCreateSerializer(serializers.Serializer):
    flightResultId = serializers.IntegerField(source='flight_result_id')
    tripType = serializers.CharField()
    passengers = PassengerSerializer(many=True)
    paymentMethod = serializers.CharField(source='payment_method')  # 'paystack' or 'wallet'
    voucherCode = serializers.CharField(required=False, allow_null=True)
    callbackUrl = serializers.URLField(required=False, allow_null=True, source='callback_url')
    
    def validate_paymentMethod(self, value):
        """Validate payment method"""
        if value not in ['paystack', 'wallet']:
            raise serializers.ValidationError('Payment method must be either "paystack" or "wallet"')
        return value

