from rest_framework import serializers
from .models import Airport, FlightSearch, FlightResult, FlightLeg


class AirportSerializer(serializers.ModelSerializer):
    airportCode = serializers.CharField(source='airport_code')
    cityCountry = serializers.CharField(source='city_country')
    
    class Meta:
        model = Airport
        fields = ['airportCode', 'description', 'cityCountry', 'city', 'country', 'priority']


class FlightLegSerializer(serializers.ModelSerializer):
    legNumber = serializers.IntegerField(source='leg_number')
    departureCode = serializers.CharField(source='departure_code')
    departureName = serializers.CharField(source='departure_name')
    destinationCode = serializers.CharField(source='destination_code')
    destinationName = serializers.CharField(source='destination_name')
    departureDate = serializers.DateField(source='departure_date')
    departureTime = serializers.TimeField(source='departure_time')
    arrivalDate = serializers.DateField(source='arrival_date')
    arrivalTime = serializers.TimeField(source='arrival_time')
    isStop = serializers.BooleanField(source='is_stop')
    cabinClass = serializers.CharField(source='cabin_class')
    cabinClassName = serializers.CharField(source='cabin_class_name')
    operatingCarrier = serializers.CharField(source='operating_carrier')
    marketingCarrier = serializers.CharField(source='marketing_carrier')
    flightNumber = serializers.CharField(source='flight_number')
    
    class Meta:
        model = FlightLeg
        fields = [
            'legNumber', 'departureCode', 'departureName', 'destinationCode',
            'destinationName', 'departureDate', 'departureTime', 'arrivalDate',
            'arrivalTime', 'duration', 'isStop', 'layover', 'cabinClass',
            'cabinClassName', 'operatingCarrier', 'marketingCarrier', 'flightNumber'
        ]


class FlightResultSerializer(serializers.ModelSerializer):
    flightId = serializers.CharField(source='flight_id')
    connectionId = serializers.CharField(source='connection_id')
    connectionCode = serializers.CharField(source='connection_code')
    priceAmount = serializers.DecimalField(source='price_amount', max_digits=12, decimal_places=2)
    priceCurrency = serializers.CharField(source='price_currency')
    airlineCode = serializers.CharField(source='airline_code')
    airlineName = serializers.CharField(source='airline_name')
    departureCode = serializers.CharField(source='departure_code')
    departureName = serializers.CharField(source='departure_name')
    departureTime = serializers.DateTimeField()
    arrivalCode = serializers.CharField(source='arrival_code')
    arrivalName = serializers.CharField(source='arrival_name')
    arrivalTime = serializers.DateTimeField()
    isRefundable = serializers.BooleanField(source='is_refundable')
    flightData = serializers.JSONField(source='flight_data')
    legs = FlightLegSerializer(many=True, read_only=True)
    
    class Meta:
        model = FlightResult
        fields = [
            'id', 'flightId', 'connectionId', 'connectionCode', 'priceAmount',
            'priceCurrency', 'airlineCode', 'airlineName', 'departureCode',
            'departureName', 'departureTime', 'arrivalCode', 'arrivalName',
            'arrivalTime', 'stops', 'trip_duration', 'isRefundable', 'flightData', 'legs'
        ]


class FlightSearchSerializer(serializers.ModelSerializer):
    searchId = serializers.CharField(source='search_id', read_only=True)
    flightSearchType = serializers.CharField(source='flight_search_type')
    ticketClass = serializers.CharField(source='ticket_class')
    departureCode = serializers.CharField(source='departure_code')
    destinationCode = serializers.CharField(source='destination_code')
    departureDate = serializers.DateField(source='departure_date')
    returnDate = serializers.DateField(source='return_date', required=False, allow_null=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    
    class Meta:
        model = FlightSearch
        fields = [
            'searchId', 'flightSearchType', 'ticketClass', 'adults', 'children',
            'infants', 'departureCode', 'destinationCode', 'departureDate',
            'returnDate', 'createdAt'
        ]


class FlightSearchRequestSerializer(serializers.Serializer):
    """Serializer for flight search API request"""
    flightSearchType = serializers.ChoiceField(choices=['Oneway', 'Return'])
    ticketclass = serializers.CharField(default='Y')
    flexibleDateFlag = serializers.CharField(default='false')
    adults = serializers.IntegerField(min_value=1, max_value=9)
    children = serializers.IntegerField(min_value=0, max_value=8)
    infants = serializers.IntegerField(min_value=0, max_value=9)
    geographyId = serializers.CharField(default='NG')
    targetCurrency = serializers.CharField(default='NGN')
    languageCode = serializers.CharField(default='en')
    itineraries = serializers.ListField(
        child=serializers.DictField()
    )
    flightRequestView = serializers.CharField(required=False)


class FlightSearchResponseSerializer(serializers.Serializer):
    """Serializer for flight search API response"""
    searchId = serializers.CharField()

