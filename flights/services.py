import requests
import json
import logging
from typing import Dict, List, Optional
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)


class WakanowAPIService:
    """Service for integrating with Wakanow Flight API"""
    
    SEARCH_BASE_URL = "https://flights.wakanow.com/api/flights"
    LOCATION_BASE_URL = "https://wakanow-api-locations-production-prod.azurewebsites.net/api/locations"
    
    def __init__(self):
        self.user_agent = UserAgent().random
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-ng',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': 'https://www.wakanow.com/',
            'x-currency': 'NGN',
            'Content-Type': 'application/json',
            'Origin': 'https://www.wakanow.com',
            'Connection': 'keep-alive',
            'User-Agent': self.user_agent
        })
    
    def search_airports(self, query: str) -> List[Dict]:
        """
        Search for airports by query
        
        Args:
            query: Search query (e.g., 'lagos', 'abuja')
        
        Returns:
            List of airport dictionaries
        """
        try:
            url = f"{self.LOCATION_BASE_URL}/airport/{query}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching airports: {e}")
            return []
    
    def search_flights(self, search_data: Dict) -> Optional[str]:
        """
        Initiate flight search and return search ID
        
        Args:
            search_data: Dictionary containing flight search parameters
        
        Returns:
            Search ID string or None if failed
        """
        try:
            url = f"{self.SEARCH_BASE_URL}/Search"
            
            # Convert FlightRequestView to string if it's a dict
            if 'FlightRequestView' in search_data and isinstance(search_data['FlightRequestView'], dict):
                search_data['FlightRequestView'] = json.dumps(search_data['FlightRequestView'])
            
            response = self.session.post(url, json=search_data, timeout=30)
            response.raise_for_status()
            
            # Response is a plain string (search ID), not JSON
            search_id = response.text.strip().strip('"')
            return search_id
        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching flights: {e}")
            return None
    
    def get_flight_results(self, search_id: str, currency: str = 'NGN') -> Optional[Dict]:
        """
        Get flight search results
        
        Args:
            search_id: Search ID from search_flights
            currency: Currency code (default: 'NGN')
        
        Returns:
            Dictionary containing flight results or None if failed
        """
        try:
            url = f"{self.SEARCH_BASE_URL}/SearchV2/{search_id}/{currency}"
            
            # Use same user agent for consistency
            headers = {
                'User-Agent': self.user_agent,
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'TE': 'trailers'
            }
            
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting flight results: {e}")
            return None
    
    def format_search_request(self, data: Dict) -> Dict:
        """
        Format flight search request data for Wakanow API
        
        Args:
            data: Dictionary containing search parameters
        
        Returns:
            Formatted dictionary ready for API call
        """
        # Build FlightRequestView object
        flight_request_view = {
            "FlightSearchType": data.get('flightSearchType', 'Oneway'),
            "Ticketclass": data.get('ticketclass', 'Y'),
            "FlexibleDateFlag": data.get('flexibleDateFlag', 'false'),
            "Adults": data.get('adults', 1),
            "Children": data.get('children', 0),
            "Infants": data.get('infants', 0),
            "GeographyId": data.get('geographyId', 'NG'),
            "TargetCurrency": data.get('targetCurrency', 'NGN'),
            "LanguageCode": data.get('languageCode', 'en'),
            "Itineraries": []
        }
        
        # Process itineraries
        for itinerary in data.get('itineraries', []):
            itinerary_data = {
                "Ticketclass": itinerary.get('ticketclass', 'Y'),
                "Departure": itinerary.get('departure'),
                "Destination": itinerary.get('destination'),
                "DepartureDate": itinerary.get('departureDate'),
            }
            
            if itinerary.get('returnDate'):
                itinerary_data["ReturnDate"] = itinerary['returnDate']
            
            # Add metadata if available
            if itinerary.get('departureMetaData'):
                itinerary_data["DepartureMetaData"] = itinerary['departureMetaData']
            if itinerary.get('destinationMetaData'):
                itinerary_data["DestinationMetaData"] = itinerary['destinationMetaData']
            
            flight_request_view["Itineraries"].append(itinerary_data)
        
        # Build main request
        request_data = {
            "FlightSearchType": data.get('flightSearchType', 'Oneway'),
            "Ticketclass": data.get('ticketclass', 'Y'),
            "FlexibleDateFlag": data.get('flexibleDateFlag', 'false'),
            "Adults": data.get('adults', 1),
            "Children": data.get('children', 0),
            "Infants": data.get('infants', 0),
            "GeographyId": data.get('geographyId', 'NG'),
            "TargetCurrency": data.get('targetCurrency', 'NGN'),
            "LanguageCode": data.get('languageCode', 'en'),
            "Itineraries": flight_request_view["Itineraries"],
            "FlightRequestView": flight_request_view
        }
        
        return request_data
    
    def convert_date_format(self, date_str: str) -> str:
        """
        Convert date format from various formats to M/D/YYYY
        
        Args:
            date_str: Date string in various formats
        
        Returns:
            Date string in M/D/YYYY format
        """
        from datetime import datetime
        
        # Try to parse common date formats
        formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%d-%m-%Y',
            '%Y/%m/%d',
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%m/%d/%Y')
            except ValueError:
                continue
        
        # If parsing fails, return as is (assume it's already in correct format)
        return date_str

