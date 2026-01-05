import logging
import time
from typing import Optional

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from .airline_config import FlightSearchConfig, TripType
from .scraper import ConcurrentAirlineScraper


class SearchAirLineView(APIView):
    """Optimized Django view for concurrent airline search"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    def get(self, request):
        # Get airline parameter from query params
        airline = request.query_params.get('airline', None)
        proxy_ip = request.query_params.get('proxyIP', None)

        # Create search config from query parameters
        search_config = self._create_search_config(request.query_params)
        if not search_config:
            return Response({"error": "Invalid search parameters"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Create scraper with proxy IP
            scraper = ConcurrentAirlineScraper(max_workers=11, proxy_ip=proxy_ip)
            # Perform search with optional airline filter
            results = scraper.search_all_airlines(search_config, airline)
            formatted_results = self._format_search_results(results, search_config)
            return Response(formatted_results)
        except Exception as e:
            self.logger.error(f"Error in GET request: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        # Get airline parameter from request data
        airline = request.data.get('airline', None)
        proxy_ip = request.data.get('proxyIP', None)

        try:
            # Create scraper with proxy IP
            scraper = ConcurrentAirlineScraper(max_workers=11, proxy_ip=proxy_ip)
            results = self._perform_search(request, scraper)
            return Response(results)
        except Exception as e:
            self.logger.error(f"Error in POST request: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _perform_search(self, request, scraper):
        search_config = self._create_search_config(request.data)
        if not search_config:
            raise ValueError("Invalid search parameters")

        # Get airline parameter from request data
        airline = request.data.get('airline', None)

        # Perform search with optional airline filter
        results = scraper.search_all_airlines(search_config, airline)
        return self._format_search_results(results, search_config)

    def _create_search_config(self, params) -> Optional[FlightSearchConfig]:
        """Create and validate search configuration from request parameters"""
        try:
            # Required parameters
            departure_city = params.get('departure_city')
            arrival_city = params.get('arrival_city')
            departure_date = params.get('departure_date')

            if not all([departure_city, arrival_city, departure_date]):
                return None

            # Optional parameters with defaults
            return_date = params.get('return_date', '10 Jun 2025')
            trip_type_str = params.get('trip_type', 'round-trip')
            adults = int(params.get('adults', 1))
            children = int(params.get('children', 0))
            infants = int(params.get('infants', 0))

            # Validate trip type
            try:
                trip_type = TripType(trip_type_str)
            except ValueError:
                trip_type = TripType.ROUND_TRIP

            # Validate passenger counts
            if adults < 1 or adults > 9:
                raise ValueError("Adults must be between 1 and 9")
            if children < 0 or children > 8:
                raise ValueError("Children must be between 0 and 8")
            if infants < 0 or infants > adults:
                raise ValueError("Infants cannot exceed number of adults")

            # Create configuration
            config = FlightSearchConfig(
                departure_city=departure_city,
                arrival_city=arrival_city,
                departure_date=departure_date,
                return_date=return_date,
                adults=adults,
                children=children,
                infants=infants,
                trip_type=trip_type
            )

            return config

        except (ValueError, TypeError) as e:
            self.logger.warning(f"Config creation error: {str(e)}")
            raise ValueError(f"Invalid parameter: {str(e)}")

    def _format_search_results(self, raw_results: dict, search_config: FlightSearchConfig) -> dict:
        """Format search results for API response"""
        try:
            # Ensure raw_results is a dictionary
            if not isinstance(raw_results, dict):
                raise ValueError(f"Expected dict, got {type(raw_results).__name__}")
            
            # Calculate summary statistics
            successful_searches = sum(1 for result in raw_results.values() if result.get('success'))
            total_airlines = len(raw_results)

            # Format final response
            formatted_response = {
                "search_summary": {
                    "departure_city": search_config.departure_city,
                    "arrival_city": search_config.arrival_city,
                    "departure_date": search_config.departure_date,
                    "return_date": search_config.return_date if search_config.trip_type == TripType.ROUND_TRIP else None,
                    "trip_type": search_config.trip_type.value,
                    "passengers": {
                        "adults": search_config.adults,
                        "children": search_config.children,
                        "infants": search_config.infants
                    },
                    "search_statistics": {
                        "total_airlines_searched": total_airlines,
                        "successful_searches": successful_searches,
                        "failed_searches": total_airlines - successful_searches,
                    }
                },
                "airline_results": raw_results,
                "search_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "status": "success" if successful_searches > 0 else "no_results"
            }

            return formatted_response

        except Exception as e:
            self.logger.error(f"Result formatting error: {str(e)}")
            return {
                "search_summary": {
                    "departure_city": search_config.departure_city,
                    "arrival_city": search_config.arrival_city,
                    "status": "formatting_error"
                },
                "error": f"Error formatting results: {str(e)}",
                "raw_results": raw_results
            }

