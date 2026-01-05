import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..airline_config import FlightSearchConfig, TripType
from .utils import extract_airport_code


class CraneScraper:
    """Scraper for Crane.aero based airlines"""

    def __init__(self, logger: logging.Logger = None, cloudflare_handler=None, webdriver_manager=None):
        self.logger = logger or logging.getLogger(__name__)
        self.cloudflare_handler = cloudflare_handler
        self.webdriver_manager = webdriver_manager

    def _build_availability_url(self, airline_config, search_config: FlightSearchConfig) -> str:
        """Build the availability URL with query parameters"""
        # URLs in airline_config are already set to /ibe/availability, so use directly
        base_url = airline_config.url
        
        # Extract airport codes
        dep_port = extract_airport_code(search_config.departure_city)
        arr_port = extract_airport_code(search_config.arrival_city)
        
        # Convert date format from "06 Jun 2025" to "06.12.2025"
        dep_date = self._convert_date_format(search_config.departure_date)
        ret_date = self._convert_date_format(search_config.return_date)
        
        # Determine which URL format to use based on airline
        # Arik Air uses passengerQuantities format
        if airline_config.key == 'arikair':
            return self._build_arikair_url(base_url, dep_port, arr_port, dep_date, ret_date, search_config)
        # Aero Contractors uses format with currency and returnDate even for one-way
        elif airline_config.key == 'flyaero':
            return self._build_aero_contractors_url(base_url, dep_port, arr_port, dep_date, ret_date, search_config)
        # UMZA and others use simple format without currency
        else:
            return self._build_simple_url(base_url, dep_port, arr_port, dep_date, ret_date, search_config)
    
    def _build_simple_url(self, base_url: str, dep_port: str, arr_port: str, dep_date: str, 
                          ret_date: str, search_config: FlightSearchConfig) -> str:
        """Build URL using simple format (used by Air Peace, UMZA, Ibom Air, NG Eagle)"""
        params = []
        
        # Trip type (comes first for UMZA format)
        trip_type = 'ONE_WAY' if search_config.trip_type == TripType.ONE_WAY else 'ROUND_TRIP'
        params.append(f'tripType={trip_type}')
        
        # Ports
        params.append(f'depPort={dep_port}')
        params.append(f'arrPort={arr_port}')
        
        # Dates
        params.append(f'departureDate={dep_date}')
        # Only include returnDate for round trips
        if search_config.trip_type == TripType.ROUND_TRIP:
            params.append(f'returnDate={ret_date}')
        
        # Passengers (simple format)
        params.append(f'adult={search_config.adults}')
        params.append(f'child={search_config.children}')
        params.append(f'infant={search_config.infants}')
        
        # Language
        params.append('lang=en')
        
        query_string = '&'.join(params)
        return f"{base_url}?{query_string}"
    
    def _build_aero_contractors_url(self, base_url: str, dep_port: str, arr_port: str, dep_date: str,
                                     ret_date: str, search_config: FlightSearchConfig) -> str:
        """Build URL using Aero Contractors format (with currency and returnDate for one-way)"""
        params = []
        
        # Currency and language (comes first for Aero Contractors)
        params.append('currency=NGN')
        params.append('lang=en')
        
        # Dates
        params.append(f'departureDate={dep_date}')
        # Aero Contractors includes returnDate even for one-way trips
        if search_config.trip_type == TripType.ROUND_TRIP:
            params.append(f'returnDate={ret_date}')
        else:
            params.append(f'returnDate={dep_date}')  # Use departure date for one-way
        
        # Ports
        params.append(f'depPort={dep_port}')
        params.append(f'arrPort={arr_port}')
        
        # Passengers (simple format)
        params.append(f'adult={search_config.adults}')
        params.append(f'child={search_config.children}')
        params.append(f'infant={search_config.infants}')
        
        # Trip type
        trip_type = 'ONE_WAY' if search_config.trip_type == TripType.ONE_WAY else 'ROUND_TRIP'
        params.append(f'tripType={trip_type}')
        
        query_string = '&'.join(params)
        return f"{base_url}?{query_string}"
    
    def _build_arikair_url(self, base_url: str, dep_port: str, arr_port: str, dep_date: str,
                           ret_date: str, search_config: FlightSearchConfig) -> str:
        """Build URL using passengerQuantities format (used by Arik Air)"""
        params = []
        
        # Trip type
        trip_type = 'ONE_WAY' if search_config.trip_type == TripType.ONE_WAY else 'ROUND_TRIP'
        params.append(f'tripType={trip_type}')
        
        # Ports and dates
        params.append(f'depPort={dep_port}')
        params.append(f'arrPort={arr_port}')
        params.append(f'departureDate={dep_date}')
        
        # Return date (empty for one-way, populated for round trip)
        if search_config.trip_type == TripType.ROUND_TRIP:
            params.append(f'returnDate={ret_date}')
        else:
            params.append('returnDate=')
        
        # Passenger quantities using array format (always include all three types)
        # ADULT
        params.append('passengerQuantities[0][passengerType]=ADULT')
        params.append('passengerQuantities[0][passengerSubType]=')
        params.append(f'passengerQuantities[0][quantity]={search_config.adults}')
        
        # CHILD
        params.append('passengerQuantities[1][passengerType]=CHILD')
        params.append('passengerQuantities[1][passengerSubType]=')
        params.append(f'passengerQuantities[1][quantity]={search_config.children}')
        
        # INFANT
        params.append('passengerQuantities[2][passengerType]=INFANT')
        params.append('passengerQuantities[2][passengerSubType]=')
        params.append(f'passengerQuantities[2][quantity]={search_config.infants}')
        
        # Additional parameters
        params.append('currency=')
        params.append('cabinClass=')
        params.append('lang=EN')
        params.append('nationality=')
        params.append('promoCode=')
        params.append('accountCode=')
        params.append('affiliateCode=')
        params.append('clickId=')
        params.append('withCalendar=')
        params.append('isMobileCalendar=')
        params.append('market=')
        params.append('isFFPoint=')
        params.append('_ga=')
        
        query_string = '&'.join(params)
        return f"{base_url}?{query_string}"
    
    def _convert_date_format(self, date_str: str) -> str:
        """Convert date from 'dd MMM yyyy' to 'dd.MM.yyyy'"""
        try:
            parts = date_str.split()
            if len(parts) != 3:
                return date_str
            
            day = parts[0]
            month_map = {
                'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
                'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
            }
            month = month_map.get(parts[1], '01')
            year = parts[2]
            
            return f"{day}.{month}.{year}"
        except Exception as e:
            self.logger.error(f"Error converting date format: {e}")
            return date_str

    def scrape(self, driver: webdriver.Chrome, airline_config, search_config: FlightSearchConfig) -> Optional[Dict]:
        """Optimized Crane.aero scraping with direct URL navigation"""
        MAX_RETRIES = 0
        retries = 0

        while retries <= MAX_RETRIES:
            try:
                print(f"🔍 Attempt {retries + 1}: {airline_config.name}")

                # For retries after the first, create a fresh driver
                if retries > 0:
                    print("♻️ Restarting browser session...")
                    driver.quit()
                    if self.webdriver_manager:
                        driver = self.webdriver_manager.create_driver(airline_config.key, airline_config.group)
                    else:
                        from ..webdriver_manager import OptimizedWebDriverManager
                        driver = OptimizedWebDriverManager().create_driver(airline_config.key, airline_config.group)

                # Build and navigate directly to availability URL
                availability_url = self._build_availability_url(airline_config, search_config)
                print(f"🌐 Navigating to: {availability_url}")
                driver.get(availability_url)

                if self.cloudflare_handler and self.cloudflare_handler.handle_protection(driver):
                    print("⚠️ Cloudflare protection detected.")
                    retries += 1
                    continue

                # Wait for results table to be present
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "availability-flight-table-0"))
                )
                # time.sleep(3)  # Wait for content to fully load

                return self.extract_results(driver, search_config.trip_type, airline_config.key)

            except Exception as e:
                self.logger.error(f"❌ Scrape attempt {retries + 1} failed: {e}")
                retries += 1

        self.logger.error(f"❌ Max retries exceeded for {airline_config.name}")
        return None

    def fill_form(self, driver: webdriver.Chrome, config: FlightSearchConfig):
        """Optimized Crane form filling"""
        try:
            # Set trip type
            if config.trip_type == TripType.ONE_WAY:
                driver.execute_script(f'document.querySelector("label[for=\\"{config.trip_type.value}\\"]")?.click();')
                time.sleep(2)

            # Use JavaScript to select the departure city
            dep_js_script = f"""
                function extractAirportCode(text) {{
                    const matches = [...text.matchAll(/\\(([^)]+)\\)/g)];
                    if (matches.length > 0) {{
                        return matches[matches.length - 1][1].toUpperCase();
                    }}
                    return '';
                }}

                var depSelect = document.getElementById('firstDepPort');
                if (depSelect) {{
                    for(var i = 0; i < depSelect.options.length; i++) {{
                        if(extractAirportCode(depSelect.options[i].text) == '{extract_airport_code(config.departure_city)}') {{
                            depSelect.selectedIndex = i;
                            depSelect.dispatchEvent(new Event('change'));
                            break;
                        }}
                    }}
                }}
            """

            driver.execute_script(dep_js_script)
            time.sleep(3)

            # Set arr city and dates in one script execution
            script = f"""
                // Set arrival city
                function extractAirportCode(text) {{
                    const matches = [...text.matchAll(/\\(([^)]+)\\)/g)];
                    if (matches.length > 0) {{
                        return matches[matches.length - 1][1].toUpperCase();
                    }}
                    return '';
                }}

                var arrSelect = document.getElementById('firstArrPort');
                if (arrSelect) {{
                    for(var i = 0; i < arrSelect.options.length; i++) {{
                        if(extractAirportCode(arrSelect.options[i].text) == '{extract_airport_code(config.arrival_city)}') {{
                            arrSelect.selectedIndex = i;
                            arrSelect.dispatchEvent(new Event('change'));
                            break;
                        }}
                    }}
                }}

                // Set departure date
                var depDate = document.getElementById('oneWayDepartureDate');
                if (depDate) {{
                    depDate.value = '{config.departure_date}';
                    depDate.dispatchEvent(new Event('change'));
                }}

                // Set return date for round trips
                {f"var retDate = document.getElementById('roundTripDepartureDate'); if (retDate) {{ retDate.value = '{config.return_date}'; retDate.dispatchEvent(new Event('change')); }}" if config.trip_type == TripType.ROUND_TRIP else ""}

                // Set passengers
                var adultInput = document.getElementById('adultCount-desktop');
                var childInput = document.getElementById('childCount-desktop');
                var infantInput = document.getElementById('infantCount-desktop');

                if (adultInput) {{ adultInput.value = '{config.adults}'; adultInput.dispatchEvent(new Event('change')); }}
                if (childInput) {{ childInput.value = '{config.children}'; childInput.dispatchEvent(new Event('change')); }}
                if (infantInput) {{ infantInput.value = '{config.infants}'; infantInput.dispatchEvent(new Event('change')); }}
            """

            driver.execute_script(script)
            time.sleep(1)

        except Exception as e:
            self.logger.error(f"Error filling Crane form: {e}")

    def submit_search(self, driver: webdriver.Chrome):
        """Submit Crane search form"""
        try:
            search_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "js-submit-button"))
            )
            search_button.click()

            # Wait for results with optimized timing
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "availability-flight-table-0"))
            )
            time.sleep(3)  # Reduced wait time

        except Exception as e:
            self.logger.error(f"Error submitting Crane search: {e}")

    def extract_results(self, driver: webdriver.Chrome, trip_type: TripType, airline_name: str) -> Dict:
        """Optimized Crane results extraction"""
        try:
            results = {}

            # Extract departure flights
            departure_flights = self._extract_flights_table(driver, "availability-flight-table-0", airline_name)
            if departure_flights:
                results['departure'] = departure_flights

            # Extract return flights for round trips
            if trip_type == TripType.ROUND_TRIP:
                return_flights = self._extract_flights_table(driver, "availability-flight-table-1", airline_name)
                if return_flights:
                    results['return'] = return_flights

            return results if results else None

        except Exception as e:
            self.logger.error(f"Error extracting Crane results: {e}")
            return None

    def _extract_flights_table(self, driver: webdriver.Chrome, table_id: str, airline_name: str) -> List[Dict]:
        """Extract flights from table using BeautifulSoup and parallel processing"""
        try:
            # Wait for table to be present
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, table_id))
            )

            # Get the table HTML
            table_html = driver.find_element(By.ID, table_id).get_attribute('outerHTML')
            soup = BeautifulSoup(table_html, 'html.parser')

            # Find all flight elements
            flight_elements = soup.select(".js-journey")

            def process_flight(flight_element):
                try:
                    return self._extract_flight_data(flight_element, airline_name)
                except Exception as e:
                    self.logger.warning(f"Error extracting individual flight: {e}")
                    return None

            # Process flights in parallel
            with ThreadPoolExecutor(max_workers=12) as executor:
                futures = [executor.submit(process_flight, el) for el in flight_elements]
                flights = [result for result in (f.result() for f in as_completed(futures)) if result]

            return flights

        except Exception as e:
            self.logger.error(f"Error extracting flights table {table_id}: {e}")
            return []

    def _extract_flight_data(self, flight_element, airline_name) -> Optional[Dict]:
        """Extract Crane flight data using BeautifulSoup"""
        try:
            # Extract route blocks
            route_blocks = flight_element.select(".desktop-route-block .info-block")
            if len(route_blocks) < 2:
                return None

            departure_block, arrival_block = route_blocks[0], route_blocks[-1]

            flight_data = {
                "flight_number": self._safe_extract_text_bs(flight_element, ".flight-no"),
                "departure": {
                    "time": self._safe_extract_text_bs(departure_block, ".time"),
                    "city": self._safe_extract_text_bs(departure_block, ".port"),
                    "date": self._safe_extract_text_bs(departure_block, ".date")
                },
                "arrival": {
                    "time": self._safe_extract_text_bs(arrival_block, ".time"),
                    "city": self._safe_extract_text_bs(arrival_block, ".port"),
                    "date": self._safe_extract_text_bs(arrival_block, ".date")
                },
                "fares": []
            }

            # Process fares in parallel
            fare_classes = ["ECONOMY", "PREMIUM", "BUSINESS"]
            if airline_name == 'arikair':
                fare_elements = flight_element.select(".fare-item")[:3]
            else:
                fare_elements = flight_element.select(".branded-fare-item")[:3]

            def process_fare(fare_element, index):
                try:
                    # Skip fares with no available seats
                    if fare_element.select_one(".no-seat-text"):
                        return None

                    # Extract price
                    if airline_name == 'arikair':
                        price_tag = (
                                fare_element.select_one(".price-best-offer") or
                                fare_element.select_one(".price-block")
                        )
                    else:
                        price_tag = (fare_element.select_one(".currency") or
                                     fare_element.select_one(".currency-best-offer"))

                    price = price_tag.text.strip() if price_tag else None

                    if price:
                        return {
                            "type": fare_classes[index] if index < len(fare_classes) else f"Class_{index + 1}",
                            "price": price
                        }
                except Exception as e:
                    self.logger.warning(f"Error processing fare at index {index}: {e}")
                    return None

            # Process fares in parallel
            with ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(process_fare, fare_element, i)
                    for i, fare_element in enumerate(fare_elements)
                ]
                fares = [result for result in (f.result() for f in as_completed(futures)) if result]

            flight_data["fares"] = fares
            return flight_data if flight_data["flight_number"] else None

        except Exception as e:
            self.logger.error(f"Error extracting Crane flight data: {e}")
            return None

    def _safe_extract_text_bs(self, element, selector: str) -> Optional[str]:
        """Safely extract text from BeautifulSoup element using CSS selector"""
        try:
            found_element = element.select_one(selector)
            return found_element.text.strip() if found_element else None
        except Exception as e:
            self.logger.warning(f"Error extracting text with selector {selector}: {e}")
            return None

