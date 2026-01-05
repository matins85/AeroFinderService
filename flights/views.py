from datetime import datetime
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import filters

from .models import Airport, FlightSearch, FlightResult, FlightLeg
from .serializers import AirportSerializer, FlightSearchSerializer, FlightResultSerializer
from .services import WakanowAPIService
from audit.models import AuditLog


class AirportViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for airport search"""
    queryset = Airport.objects.all()
    serializer_class = AirportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['airport_code', 'description', 'city', 'country', 'city_country']
    ordering_fields = ['priority', 'airport_code']
    
    def get_queryset(self):
        queryset = Airport.objects.all()
        search = self.request.query_params.get('search')
        country = self.request.query_params.get('country')
        
        if search:
            queryset = queryset.filter(
                Q(airport_code__icontains=search) |
                Q(description__icontains=search) |
                Q(city__icontains=search) |
                Q(country__icontains=search)
            )
        
        if country:
            queryset = queryset.filter(country__icontains=country)
        
        return queryset.order_by('-priority', 'airport_code')


class FlightSearchViewSet(viewsets.ModelViewSet):
    """ViewSet for flight search"""
    queryset = FlightSearch.objects.all()
    serializer_class = FlightSearchSerializer
    permission_classes = [IsAuthenticated]
    wakanow_service = WakanowAPIService()
    
    def create(self, request, *args, **kwargs):
        """Initiate flight search"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Create flight search record
        flight_search = serializer.save(user=request.user)
        
        # Format request for Wakanow API
        search_data = self.wakanow_service.format_search_request(request.data)
        
        # Call Wakanow API
        search_id = self.wakanow_service.search_flights(search_data)
        
        if not search_id:
            return Response(
                {'error': 'Failed to initiate flight search'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Update search_id from Wakanow response
        flight_search.search_id = search_id
        flight_search.save()
        
        # Create audit log
        AuditLog.objects.create(
            user=request.user,
            action='CREATE_FLIGHT_SEARCH',
            resource_type='FlightSearch',
            resource_id=str(flight_search.id),
            description=f'Created flight search {flight_search.search_id}',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response({'searchId': search_id}, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'], url_path='results')
    def results(self, request, pk=None):
        """Get flight search results"""
        flight_search = self.get_object()
        currency = request.query_params.get('currency', 'NGN')
        
        # Get results from Wakanow API
        results_data = self.wakanow_service.get_flight_results(
            flight_search.search_id, currency
        )
        
        if not results_data:
            return Response(
                {'hasResult': False, 'searchFlightResults': []},
                status=status.HTTP_200_OK
            )
        
        # Process and save results to database
        if results_data.get('HasResult') and results_data.get('SearchFlightResults'):
            self._process_flight_results(flight_search, results_data['SearchFlightResults'])
        
        # Return formatted response
        return Response({
            'hasResult': results_data.get('HasResult', False),
            'searchFlightResults': results_data.get('SearchFlightResults', []),
            'flightRequestView': results_data.get('FlightRequestView', '')
        })
    
    def _process_flight_results(self, flight_search, results):
        """Process and save flight results to database"""
        for result_data in results:
            flight_combination = result_data.get('FlightCombination', {})
            flights = flight_combination.get('Flights', [])
            
            if not flights:
                continue
            
            # Get first flight for basic info
            first_flight = flights[0]
            price = flight_combination.get('Price', {})
            
            # Parse datetime strings (handle various formats)
            def parse_datetime(dt_str):
                """Parse datetime string in various formats"""
                if not dt_str:
                    return timezone.now()
                try:
                    # Try ISO format first
                    return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    try:
                        # Try common formats
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%m/%d/%Y %H:%M:%S']:
                            try:
                                return datetime.strptime(dt_str, fmt)
                            except ValueError:
                                continue
                    except Exception:
                        pass
                return timezone.now()
            
            def parse_date(date_str):
                """Parse date string"""
                if not date_str:
                    return timezone.now().date()
                try:
                    dt = parse_datetime(date_str)
                    return dt.date()
                except Exception:
                    return timezone.now().date()
            
            def parse_time(time_str):
                """Parse time string"""
                if not time_str:
                    return timezone.now().time()
                try:
                    dt = parse_datetime(time_str)
                    return dt.time()
                except Exception:
                    return timezone.now().time()
            
            # Create FlightResult
            flight_result = FlightResult.objects.create(
                search=flight_search,
                flight_id=result_data.get('FlightId', ''),
                connection_id=flight_combination.get('ConnectionId', ''),
                connection_code=flight_combination.get('ConnectionCode', ''),
                price_amount=Decimal(str(price.get('Amount', 0))),
                price_currency=price.get('CurrencyCode', 'NGN'),
                airline_code=first_flight.get('Airline', ''),
                airline_name=first_flight.get('AirlineName', ''),
                departure_code=first_flight.get('DepartureCode', ''),
                departure_name=first_flight.get('DepartureName', ''),
                departure_time=parse_datetime(first_flight.get('DepartureTime', '')),
                arrival_code=first_flight.get('ArrivalCode', ''),
                arrival_name=first_flight.get('ArrivalName', ''),
                arrival_time=parse_datetime(first_flight.get('ArrivalTime', '')),
                stops=first_flight.get('Stops', 0),
                trip_duration=first_flight.get('TripDuration', ''),
                is_refundable=flight_combination.get('IsRefundable', False),
                flight_data=result_data
            )
            
            # Create FlightLegs
            for flight in flights:
                flight_legs = flight.get('FlightLegs', [])
                for idx, leg_data in enumerate(flight_legs, start=1):
                    FlightLeg.objects.create(
                        flight_result=flight_result,
                        leg_number=idx,
                        departure_code=leg_data.get('DepartureCode', ''),
                        departure_name=leg_data.get('DepartureName', ''),
                        destination_code=leg_data.get('DestinationCode', ''),
                        destination_name=leg_data.get('DestinationName', ''),
                        departure_date=parse_date(leg_data.get('DepartureDate', '')),
                        departure_time=parse_time(leg_data.get('DepartureTime', '')),
                        arrival_date=parse_date(leg_data.get('ArrivalDate', '')),
                        arrival_time=parse_time(leg_data.get('ArrivalTime', '')),
                        duration=leg_data.get('Duration', ''),
                        is_stop=leg_data.get('IsStop', False),
                        layover=leg_data.get('Layover'),
                        cabin_class=leg_data.get('CabinClass', ''),
                        cabin_class_name=leg_data.get('CabinClassName', ''),
                        operating_carrier=leg_data.get('OperatingCarrier', ''),
                        marketing_carrier=leg_data.get('MarketingCarrier', ''),
                        flight_number=leg_data.get('FlightNumber', '')
                    )
    
    @staticmethod
    def _get_client_ip(request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

