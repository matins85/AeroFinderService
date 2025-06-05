import logging
import time
import shutil
import subprocess
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
import os
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from twocaptcha import TwoCaptcha
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse


def wait(min_time=2, max_time=4):
    time.sleep(random.uniform(min_time, max_time))


# Configuration and Constants
class TripType(Enum):
    ONE_WAY = "one-way"
    ROUND_TRIP = "round-trip"


class AirlineGroup(Enum):
    CRANE_AERO = "crane_aero"
    VIDECOM = "videcom"
    OVERLAND = "overland"  # New airline group


@dataclass
class FlightSearchConfig:
    """Configuration for flight search parameters"""
    departure_city: str = "Lagos (LOS)"
    arrival_city: str = "Abuja (ABV)"
    departure_date: str = "06 Jun 2025"  # Format: dd MMM yyyy for Crane, dd-MMM-yyyy for Videcom
    return_date: str = "10 Jun 2025"
    adults: int = 1
    children: int = 0
    infants: int = 0
    trip_type: TripType = TripType.ROUND_TRIP


@dataclass
class AirlineConfig:
    """Configuration for each airline"""
    name: str
    url: str
    group: AirlineGroup
    key: str  # Key for response dict


# Airline configurations - All 9 airlines
AIRLINES_CONFIG = [
    # Crane.aero based airlines (5 airlines)
    AirlineConfig("Air Peace", "https://book-airpeace.crane.aero/ibe/search", AirlineGroup.CRANE_AERO, "airpeace"),
    AirlineConfig("Arik Air", "https://arikair.crane.aero/ibe/search", AirlineGroup.CRANE_AERO, "arikair"),
    AirlineConfig("Aero Contractors", "https://flyaero.crane.aero/ibe/search", AirlineGroup.CRANE_AERO, "flyaero"),
    AirlineConfig("Ibom Air", "https://book-ibomair.crane.aero/ibe/search", AirlineGroup.CRANE_AERO, "ibomair"),
    AirlineConfig("NG Eagle", "https://book-ngeagle.crane.aero/ibe/search", AirlineGroup.CRANE_AERO, "ngeagle"),

    # Videcom based airlines (3 airlines)
    AirlineConfig("Max Air", "https://customer2.videcom.com/MaxAir/VARS/Public/CustomerPanels/requirementsBS.aspx",
                  AirlineGroup.VIDECOM, "maxair"),
    AirlineConfig("United Nigeria",
                  "https://booking.flyunitednigeria.com/VARS/Public/CustomerPanels/requirementsBS.aspx",
                  AirlineGroup.VIDECOM, "unitednigeria"),
    AirlineConfig("Rano Air", "https://customer3.videcom.com/RanoAir/VARS/Public/CustomerPanels/requirementsBS.aspx",
                  AirlineGroup.VIDECOM, "ranoair"),

    # Overland Airways
    AirlineConfig("Overland Airways", "https://www.overlandairways.com/", AirlineGroup.OVERLAND, "overland"),
]


class OptimizedWebDriverManager:
    """Optimized WebDriver manager with better resource management"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.logger = logging.getLogger(__name__)

    def create_driver(self) -> webdriver.Chrome:
        """Create optimized Chrome WebDriver"""
        user_agent = UserAgent()
        options = Options()

        # Optimized Chrome options for better performance
        chrome_options = [
            f"--user-agent={user_agent.random}",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--window-size=1366,768",  # Smaller window for better performance
            "--ignore-certificate-errors",
            "--allow-running-insecure-content",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-images",  # Disable images for faster loading
            "--disable-javascript",  # We'll enable JS selectively
            "--disable-css",  # Disable CSS loading
            '--proxy-server="direct://"',
            "--proxy-bypass-list=*",
            "--disable-logging",
            "--disable-dev-tools",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=TranslateUI",
            "--disable-default-apps",
            "--disable-sync",
            "--memory-pressure-off",
            "--max_old_space_size=4096",
        ]

        if self.headless:
            chrome_options.extend([
                "--headless=new",
                "--disable-software-rasterizer",
                "--disable-web-security",
            ])

        for option in chrome_options:
            options.add_argument(option)

        # Performance preferences
        prefs = {
            "profile.default_content_setting_values": {
                "images": 2,  # Block images
                "plugins": 2,  # Block plugins
                "popups": 2,  # Block popups
                "geolocation": 2,  # Block location sharing
                "notifications": 2,  # Block notifications
                "media_stream": 2,  # Block media stream
            },
        }
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        service = self._create_service()

        # try:
        #     # Try to use webdriver-manager for automatic driver management
        #     from webdriver_manager.chrome import ChromeDriverManager
        #     service = Service(ChromeDriverManager().install())
        #     driver = webdriver.Chrome(service=service, options=options)
        # except ImportError:
        #     # Fallback to system Chrome driver
        #     driver = webdriver.Chrome(options=options)

        try:
            driver = webdriver.Chrome(service=service, options=options)
            self.logger.info("Successfully created Chrome driver")
        except Exception as e:
            self.logger.error(f"Failed to create Chrome driver: {e}")
            raise

        # Optimized timeouts
        driver.set_page_load_timeout(20)  # Reduced timeout
        driver.implicitly_wait(5)  # Reduced implicit wait

        # Execute script to remove automation detection
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        return driver

    def _create_service(self):
        """Create Chrome service with multiple fallback options"""

        # Option 1: Try system ChromeDriver (installed via brew)
        chromedriver_path = shutil.which('chromedriver')
        if chromedriver_path:
            self.logger.info(f"Using system ChromeDriver: {chromedriver_path}")
            return Service(chromedriver_path)

        # Option 2: Try common installation paths
        common_paths = [
            '/usr/local/bin/chromedriver',
            '/opt/homebrew/bin/chromedriver',  # Apple Silicon Macs
            '/usr/bin/chromedriver',
        ]

        for path in common_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                self.logger.info(f"Using ChromeDriver at: {path}")
                return Service(path)

        # Option 3: Try webdriver-manager but with better error handling
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()

            # Verify the path is executable
            if os.access(driver_path, os.X_OK):
                self.logger.info(f"Using webdriver-manager ChromeDriver: {driver_path}")
                return Service(driver_path)
            else:
                self.logger.warning(f"ChromeDriver at {driver_path} is not executable")
        except Exception as e:
            self.logger.warning(f"webdriver-manager failed: {e}")

        # Option 4: No service (let Selenium find ChromeDriver)
        self.logger.warning("Using default Chrome service (no explicit path)")
        return None

    def _check_chrome_installation(self):
        """Check if Chrome is properly installed"""
        try:
            # Check if Chrome is installed
            result = subprocess.run(['google-chrome', '--version'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.logger.info(f"Chrome version: {result.stdout.strip()}")
                return True
        except:
            pass

        try:
            # Try alternative Chrome command
            result = subprocess.run(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.logger.info(f"Chrome version: {result.stdout.strip()}")
                return True
        except:
            pass

        self.logger.error("Google Chrome not found. Please install Chrome first.")
        return False


class OptimizedCloudflareHandler:
    """Optimized Cloudflare challenge handler"""

    def __init__(self, api_key: str = os.environ.get("CAPCHA_KEY")):
        self.api_key = api_key
        self.solver = TwoCaptcha(api_key)
        self.logger = logging.getLogger(__name__)

    def handle_protection(self, driver: webdriver.Chrome, max_wait: int = 15) -> bool:
        """Handle Cloudflare protection with optimized timing"""
        try:
            # Quick check for Cloudflare elements
            cloudflare_indicators = [
                "cf-turnstile",
                "cf-challenge-form",
                "cf-wrapper",
                "challenge-form"
            ]

            for indicator in cloudflare_indicators:
                try:
                    element = WebDriverWait(driver, 1.5).until(
                        EC.presence_of_element_located((By.CLASS_NAME, indicator))
                    )
                    if element:
                        return self._solve_challenge(driver, element)
                except:
                    continue

            return True  # No challenge found

        except Exception as e:
            self.logger.warning(f"Cloudflare handling error: {e}")
            return True  # Continue anyway

    def _solve_challenge(self, driver: webdriver.Chrome, element) -> bool:
        """Solve the actual challenge"""
        try:
            site_key = element.get_attribute("data-sitekey")
            if not site_key:
                # Try alternative attributes
                site_key = element.get_attribute("data-site-key")

            if site_key:
                current_url = driver.current_url
                solution = self.solver.turnstile(sitekey=site_key, url=current_url)

                if solution and 'code' in solution:
                    # Inject solution
                    js_script = f"""
                        var responseField = document.querySelector('[name="cf-turnstile-response"]');
                        if (responseField) {{
                            responseField.value = '{solution['code']}';
                            var form = responseField.closest('form');
                            if (form) form.submit();
                        }}
                    """
                    driver.execute_script(js_script)
                    time.sleep(3)
                    return True

            return False
        except Exception as e:
            self.logger.error(f"Challenge solving error: {e}")
            return False


class ConcurrentAirlineScraper:
    """Main scraper class that handles all airline types concurrently"""

    def __init__(self, max_workers: int = 12):
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)
        self.cloudflare_handler = OptimizedCloudflareHandler()

    def search_all_airlines(self, search_config: FlightSearchConfig, airline: Optional[str] = None) -> Dict:
        """
        Search flights across all airlines concurrently
        Args:
            search_config: Flight search configuration
            airline: Optional airline name to filter results (e.g., "airpeace", "arikair", etc.)
        Returns:
            Dictionary containing flight results from all airlines
        """
        results = {}
        self.logger.info("Starting concurrent airline search...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Filter airlines if specific airline is requested
            airlines_to_search = [config for config in AIRLINES_CONFIG if not airline or config.key == airline.lower()]
            
            if not airlines_to_search:
                self.logger.warning(f"No airlines found matching '{airline}'")
                return {"error": f"No airlines found matching '{airline}'"}
            
            self.logger.info(f"Searching {len(airlines_to_search)} airlines concurrently")
            
            future_to_airline = {
                executor.submit(self._search_single_airline, airline_config, search_config): airline_config
                for airline_config in airlines_to_search
            }

            for future in as_completed(future_to_airline):
                airline_config = future_to_airline[future]
                try:
                    result = future.result()
                    if result:
                        results[airline_config.key] = result
                        self.logger.info(f"✅ {airline_config.name} search completed successfully")
                        # Yield the result immediately
                        yield airline_config.key, result
                except Exception as e:
                    self.logger.error(f"❌ Error searching {airline_config.name}: {str(e)}")
                    error_result = {"error": str(e)}
                    results[airline_config.key] = error_result
                    yield airline_config.key, error_result

        self.logger.info("All airline searches completed")
        return results

    def _search_single_airline(self, airline_config: AirlineConfig, search_config: FlightSearchConfig) -> Dict:
        """Search a single airline with optimized error handling"""
        result = {
            "airline": airline_config.name,
            "success": False,
            "data": None,
            "error": None,
            "search_time": None
        }

        driver = None
        start_time = time.time()

        try:
            # Create optimized driver
            driver_manager = OptimizedWebDriverManager(headless=True)
            driver = driver_manager.create_driver()

            # Choose scraping strategy based on airline group
            if airline_config.group == AirlineGroup.CRANE_AERO:
                flight_data = self._scrape_crane_airline(driver, airline_config, search_config)
            elif airline_config.group == AirlineGroup.VIDECOM:
                flight_data = self._scrape_videcom_airline(driver, airline_config, search_config)
            elif airline_config.group == AirlineGroup.OVERLAND:
                flight_data = self._scrape_overland_airline(driver, airline_config, search_config)
            else:
                raise ValueError(f"Unknown airline group: {airline_config.group}")

            if flight_data:
                result["success"] = True
                result["data"] = flight_data
            else:
                result["error"] = "No flight data extracted"

        except Exception as e:
            result["error"] = f"Scraping error: {str(e)}"
            self.logger.error(f"Error scraping {airline_config.name}: {e}")

        finally:
            result["search_time"] = round(time.time() - start_time, 2)
            if driver:
                try:
                    driver.quit()
                except:
                    pass

        return result

    def _scrape_crane_airline(self, driver: webdriver.Chrome, airline_config: AirlineConfig,
                              search_config: FlightSearchConfig) -> Optional[Dict]:
        """Optimized Crane.aero scraping"""
        try:
            self.logger.info(f"🔍 Searching {airline_config.name}...")
            driver.get(airline_config.url)

            # Handle Cloudflare protection
            if not self.cloudflare_handler.handle_protection(driver):
                return None

            # Wait for search form
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "trip-type-wrapper"))
            )

            # Fill form efficiently
            self._fill_crane_form_optimized(driver, search_config)

            # Submit and wait for results
            self._submit_crane_search(driver)

            # Extract results
            return self._extract_crane_results_optimized(driver, search_config.trip_type)

        except Exception as e:
            self.logger.error(f"Crane scraping error for {airline_config.name}: {e}")
            return None

    def _scrape_videcom_airline(self, driver: webdriver.Chrome, airline_config: AirlineConfig,
                                search_config: FlightSearchConfig) -> Optional[Dict]:
        """Optimized Videcom scraping"""
        try:
            self.logger.info(f"🔍 Searching {airline_config.name}...")
            driver.get(airline_config.url)

            # Wait for form elements
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "Origin"))
            )

            # Fill form efficiently
            self._fill_videcom_form_optimized(driver, search_config)

            # Submit and wait for results
            self._submit_videcom_search(driver)

            # Extract results
            return self._extract_videcom_results_optimized(driver, search_config.trip_type)

        except Exception as e:
            self.logger.error(f"Videcom scraping error for {airline_config.name}: {e}")
            return None

    def _scrape_overland_airline(self, driver: webdriver.Chrome, airline_config: AirlineConfig,
                                 search_config: FlightSearchConfig) -> Optional[Dict]:
        """Scrape Overland Airways flights"""
        try:
            driver.get(airline_config.url)

            # Wait for the page to be fully loaded
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Handle cookie consent popup
            try:
                cookie_banner = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "cookieBanner"))
                )
                if cookie_banner.is_displayed():
                    accept_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".cookiesbtn-primary"))
                    )
                    accept_button.click()
                    time.sleep(1)
            except:
                pass

            # Fill form efficiently
            self._fill_overland_form(driver, search_config)

            # Submit and wait for results
            self._submit_overland_search(driver)

            # Extract results
            return self._extract_overland_results(driver, search_config.trip_type)

        except Exception as e:
            self.logger.error(f"Overland scraping error: {e}")
            return None

    def _fill_crane_form_optimized(self, driver: webdriver.Chrome, config: FlightSearchConfig):
        """Optimized Crane form filling"""
        try:
            # Set trip type
            if config.trip_type == TripType.ONE_WAY:
                driver.execute_script(f'document.querySelector("label[for=\\"{config.trip_type.value}\\"]")?.click();')
                time.sleep(2)

            # Use JavaScript to select the Abuja option
            dep_js_script = f"""
                var depSelect = document.getElementById('firstDepPort');
                if (depSelect) {{
                    for(var i = 0; i < depSelect.options.length; i++) {{
                        if(depSelect.options[i].text === '{config.departure_city}') {{
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
                var arrSelect = document.getElementById('firstArrPort');
                if (arrSelect) {{
                    for(var i = 0; i < arrSelect.options.length; i++) {{
                        if(arrSelect.options[i].text === '{config.arrival_city}') {{
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

    def _fill_videcom_form_optimized(self, driver: webdriver.Chrome, config: FlightSearchConfig):
        """Optimized Videcom form filling"""
        try:
            # Convert date format for Videcom
            dep_date = self._format_date_for_videcom(config.departure_date)
            ret_date = self._format_date_for_videcom(config.return_date)

            # Select trip type
            if config.trip_type == TripType.ONE_WAY:
                one_way_label = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//label[@for='ReturnTrip2']"))
                )
                one_way_label.click()
                wait(2, 3)

            dep_js_script = f"""
                var originSelect = document.getElementById('Origin');
                if (originSelect) {{
                    for(var i = 0; i < originSelect.options.length; i++) {{
                        if(originSelect.options[i].text === '{config.departure_city}') {{
                            originSelect.selectedIndex = i;
                            originSelect.dispatchEvent(new Event('change'));
                            break;
                        }}
                    }}
                }}

            """

            driver.execute_script(dep_js_script)
            time.sleep(2)

            script = f"""
                // Set cities
                var destSelect = document.getElementById('Destination');
                if (destSelect) {{
                    for(var i = 0; i < destSelect.options.length; i++) {{
                        if(destSelect.options[i].text === '{config.arrival_city}') {{
                            destSelect.selectedIndex = i;
                            destSelect.dispatchEvent(new Event('change'));
                            break;
                        }}
                    }}
                }}

                // Set dates
                var depDateField = document.getElementById('departuredate');
                if (depDateField) depDateField.value = '{dep_date}';

                {f"var retDateField = document.getElementById('returndate'); if (retDateField) retDateField.value = '{ret_date}';" if config.trip_type == TripType.ROUND_TRIP else ""}

                // Set passengers
                var adultSelect = document.getElementById('NumberOfAdults');
                if (adultSelect) adultSelect.value = '{config.adults}';

                var childSelect = document.getElementById('NumberOfChildren');
                if (childSelect) childSelect.value = '{config.children}';

                var infantSelect = document.getElementById('NumberOfInfants');
                if (infantSelect) infantSelect.value = '{config.infants}';
            """

            driver.execute_script(script)
            time.sleep(2)

        except Exception as e:
            self.logger.error(f"Error filling Videcom form: {e}")

    def _format_date_for_videcom(self, date_str: str) -> str:
        """Convert date format for Videcom (dd MMM yyyy to dd-MMM-yyyy)"""
        try:
            parts = date_str.split()
            if len(parts) == 3:
                return f"{parts[0]}-{parts[1]}-{parts[2]}"
            return date_str
        except:
            return date_str

    def _submit_crane_search(self, driver: webdriver.Chrome):
        """Submit Crane search form"""
        try:
            search_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "js-submit-button"))
            )
            search_button.click()

            # Wait for results with optimized timing
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "availability-flight-table-0"))
            )
            time.sleep(3)  # Reduced wait time

        except Exception as e:
            self.logger.error(f"Error submitting Crane search: {e}")

    def _submit_videcom_search(self, driver: webdriver.Chrome):
        """Submit Videcom search form"""
        try:
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "submitButton"))
            )
            submit_button.click()

            # Wait for results
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "calView_0"))
            )
            time.sleep(3)

        except Exception as e:
            self.logger.error(f"Error submitting Videcom search: {e}")

    def _extract_crane_results_optimized(self, driver: webdriver.Chrome, trip_type: TripType) -> Dict:
        """Optimized Crane results extraction"""
        try:
            results = {}

            # Extract departure flights
            departure_flights = self._extract_flights_table(driver, "availability-flight-table-0", "crane")
            if departure_flights:
                results['departure'] = departure_flights

            # Extract return flights for round trips
            if trip_type == TripType.ROUND_TRIP:
                return_flights = self._extract_flights_table(driver, "availability-flight-table-1", "crane")
                if return_flights:
                    results['return'] = return_flights

            return results if results else None

        except Exception as e:
            self.logger.error(f"Error extracting Crane results: {e}")
            return None

    def _extract_videcom_results_optimized(self, driver: webdriver.Chrome, trip_type: TripType) -> Dict:
        """Optimized Videcom results extraction"""
        try:
            results = {}

            # Extract departure flights
            departure_flights = self._extract_flights_table(driver, "calView_0", "videcom")
            if departure_flights:
                results['departure'] = departure_flights

            # Extract return flights for round trips
            if trip_type == TripType.ROUND_TRIP:
                return_flights = self._extract_flights_table(driver, "calView_1", "videcom")
                if return_flights:
                    results['return'] = return_flights

            return results if results else None

        except Exception as e:
            self.logger.error(f"Error extracting Videcom results: {e}")
            return None

    def _extract_flights_table(self, driver: webdriver.Chrome, table_id: str, airline_type: str) -> List[Dict]:
        """Extract flights from table - works for both Crane and Videcom"""

        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, table_id))
        )

        try:
            table = driver.find_element(By.ID, table_id)

            if airline_type == "crane":
                flight_elements = table.find_elements(By.CLASS_NAME, "js-journey")
            else:  # videcom
                flight_elements = table.find_elements(By.CLASS_NAME, "flt-panel")

            flights = []

            def process_flight(flight_element):
                try:
                    if airline_type == "crane":
                        return self._extract_crane_flight_data(flight_element)
                    else:
                        return self._extract_videcom_flight_data(flight_element)
                except Exception as e:
                    self.logger.warning(f"Error extracting individual flight: {e}")
                    return None

            # Thread pool for parallel extraction
            with ThreadPoolExecutor(max_workers=12) as executor:
                futures = [executor.submit(process_flight, el) for el in flight_elements]

                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        flights.append(result)

            return flights

        except Exception as e:
            self.logger.error(f"Error extracting flights table {table_id}: {e}")
            return []

    def _extract_crane_flight_data(self, flight_element) -> Optional[Dict]:
        """Optimized extraction of Crane flight data with ThreadPoolExecutor for fares"""

        try:
            sel = flight_element

            # Pre-select route blocks
            route_blocks = sel.find_elements(By.CSS_SELECTOR, ".desktop-route-block .info-block")
            if len(route_blocks) < 2:
                return None

            departure_block, arrival_block = route_blocks[0], route_blocks[-1]

            flight_data = {
                "flight_number": self._safe_extract_text(sel, ".flight-no"),
                "departure": {
                    "time": self._safe_extract_text(departure_block, ".time"),
                    "city": self._safe_extract_text(departure_block, ".port"),
                    "date": self._safe_extract_text(departure_block, ".date")
                },
                "arrival": {
                    "time": self._safe_extract_text(arrival_block, ".time"),
                    "city": self._safe_extract_text(arrival_block, ".port"),
                    "date": self._safe_extract_text(arrival_block, ".date")
                },
                "duration": self._safe_extract_text(sel, ".flight-duration"),
                "type": self._safe_extract_text(sel, ".total-stop"),
                "fares": []
            }

            fare_classes = ["ECONOMY", "BUSINESS", "FIRST CLASS"]
            fare_elements = sel.find_elements(By.CLASS_NAME, "branded-fare-item")[:3]

            fares = []
            for i, fare_element in enumerate(fare_elements):
                try:
                    # Skip if no seats available
                    if fare_element.find_elements(By.CLASS_NAME, "no-seat-text"):
                        continue

                    # Extract price with single query
                    price = (self._safe_extract_text(fare_element, ".currency") or
                             self._safe_extract_text(fare_element, ".currency-best-offer"))

                    if price:
                        fares.append({
                            "type": fare_classes[i] if i < len(fare_classes) else f"Class_{i + 1}",
                            "price": price,
                            "seats_available": "Available"
                        })
                except Exception:
                    continue

            flight_data["fares"] = fares
            return flight_data if flight_data["flight_number"] else None

        except Exception:
            return None

    def _extract_videcom_flight_data(self, flight_element) -> Optional[Dict]:
        """Extract Videcom flight data efficiently"""
        try:
            # Click to expand if needed
            try:
                panel_heading = flight_element.find_element(By.CLASS_NAME, "flt-panel-heading")
                panel_heading.click()
                time.sleep(0.5)
            except:
                pass

            flight_data = {
                "flight_number": self._safe_extract_text(flight_element, ".flightnumber"),
                "departure": {
                    "time": self._safe_extract_text(flight_element, ".cal-Depart-time .time"),
                    "city": self._safe_extract_text(flight_element, ".cal-Depart-time .city"),
                    "date": self._safe_extract_text(flight_element, ".cal-Depart-time .flightDate")
                },
                "arrival": {
                    "time": self._safe_extract_text(flight_element, ".cal-Arrive-time .time"),
                    "city": self._safe_extract_text(flight_element, ".cal-Arrive-time .city"),
                    "date": self._safe_extract_text(flight_element, ".cal-Arrive-time .flightDate")
                },
                "duration": self._safe_extract_text(flight_element, ".flightDuration"),
                "type": "Non-stop",  # Default for most flights
                "fares": []
            }

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = []

                for panel_num in range(1, 5):
                    futures.append(executor.submit(
                        lambda pn=panel_num: (
                            (lambda: (
                                fare_element := flight_element.find_element(By.CLASS_NAME, f"classband-panel-{pn}"),
                                price := self._safe_extract_text(fare_element, ".FareClass-price"),
                                {
                                    "type": fare_element.get_attribute("data-classband") or f"Class_{pn}",
                                    "price": price,
                                    "seats_available": "Available"
                                } if price else None
                            ))()
                        )
                    ))

                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result and isinstance(result, tuple):
                            result = result[2]
                        if result:
                            flight_data["fares"].append(result)
                    except:
                        continue

            return flight_data if flight_data.get("flight_number") else None

        except Exception as e:
            return None

    def _safe_extract_text(self, element, selector: str) -> Optional[str]:
        """Safely extract text from element using CSS selector"""
        try:
            found_element = element.find_element(By.CSS_SELECTOR, selector)
            return (found_element.text or found_element.get_attribute("textContent") or "").strip() or None
        except:
            return None

    def _fill_overland_form(self, driver: webdriver.Chrome, config: FlightSearchConfig):
        """Fill Overland Airways search form"""
        try:
            # Set trip type
            trip_type_select = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".flightType .comboHolder select"))
            )

            js_script = """
                const select = arguments[0];
                const value = arguments[1];
                select.value = value;
                select.dispatchEvent(new Event('change', { bubbles: true }));
                select.dispatchEvent(new Event('input', { bubbles: true }));
                const form = select.closest('form');
                if (form) {
                    form.dispatchEvent(new Event('change', { bubbles: true }));
                }
                return true;
            """
            trip_type = "OW" if config.trip_type == TripType.ONE_WAY else "RT"
            driver.execute_script(js_script, trip_type_select, trip_type)
            wait(1, 2)

            # Set departure city - Overland uses uppercase city names without codes
            departure_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "flightFrom"))
            )
            departure_input.click()
            wait(1, 2)

            # Extract city name without code (e.g., "Lagos" from "Lagos (LOS)")
            departure_city = config.departure_city.split(" (")[0].upper()
            js_script = f"""
                const container = document.getElementById('eac-container-flightFrom');
                if (!container) return false;
                const options = Array.from(container.querySelectorAll('.eac-item'));
                const cityOption = options.find(option => option.textContent.includes('{departure_city}'));
                if (cityOption) {{
                    cityOption.click();
                    return true;
                }}
                return false;
            """
            driver.execute_script(js_script)
            wait(1, 2)

            # Set arrival city - Overland uses uppercase city names without codes
            arrival_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "flightTo"))
            )
            arrival_input.click()
            wait(1, 2)

            # Extract city name without code (e.g., "Abuja" from "Abuja (ABV)")
            arrival_city = config.arrival_city.split(" (")[0].upper()
            js_script = f"""
                const container = document.getElementById('eac-container-flightTo');
                if (!container) return false;
                const options = Array.from(container.querySelectorAll('.eac-item'));
                const cityOption = options.find(option => option.textContent.includes('{arrival_city}'));
                if (cityOption) {{
                    cityOption.click();
                    return true;
                }}
                return false;
            """
            driver.execute_script(js_script)
            wait(1, 2)

            # Set dates - Overland uses dd/MM/yyyy format
            try:
                # Convert date from "dd MMM yyyy" to "dd/MM/yyyy"
                dep_date_parts = config.departure_date.split()
                dep_month = {
                    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
                    'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                }[dep_date_parts[1]]
                dep_date = f"{dep_date_parts[0]}/{dep_month}/{dep_date_parts[2]}"

                driver.execute_script(f"document.getElementById('flightDepart').value = '{dep_date}';")
                driver.execute_script("document.getElementById('flightDepart').dispatchEvent(new Event('change'));")

                if config.trip_type == TripType.ROUND_TRIP:
                    ret_date_parts = config.return_date.split()
                    ret_month = {
                        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
                        'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                    }[ret_date_parts[1]]
                    ret_date = f"{ret_date_parts[0]}/{ret_month}/{ret_date_parts[2]}"

                    driver.execute_script(f"document.getElementById('flightReturn').value = '{ret_date}';")
                    driver.execute_script("document.getElementById('flightReturn').dispatchEvent(new Event('change'));")
            except Exception as e:
                self.logger.error(f"Error setting dates: {e}")
                raise

            time.sleep(2)

            # Set passengers
            passengers_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "flightForm_passengers"))
            )
            passengers_input.click()
            time.sleep(0.5)

            # Set adults
            if config.adults > 1:
                for _ in range(config.adults - 1):
                    adult_plus = WebDriverWait(driver, 1).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".passPop_plus[aria-controls='passAdults']"))
                    )
                    adult_plus.click()

            # Set children
            if config.children > 0:
                for _ in range(config.children):
                    child_plus = WebDriverWait(driver, 1).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".passPop_plus[aria-controls='passChildren']"))
                    )
                    child_plus.click()

            # Set infants
            if config.infants > 0:
                for _ in range(config.infants):
                    infant_plus = WebDriverWait(driver, 1).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".passPop_plus[aria-controls='passInfants']"))
                    )
                    infant_plus.click()

        except Exception as e:
            self.logger.error(f"Error filling Overland form: {e}")
            raise

    def _submit_overland_search(self, driver: webdriver.Chrome):
        """Submit Overland search form"""
        try:
            js_script = """
                const searchButton = document.querySelector('#avl input[type="submit"]');
                if (searchButton) {
                    searchButton.click();
                    return true;
                }
                return false;
            """
            driver.execute_script(js_script)

            # Wait for search results
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "flightItem"))
            )
            time.sleep(3)

        except Exception as e:
            self.logger.error(f"Error submitting Overland search: {e}")
            raise

    def _extract_overland_results(self, driver: webdriver.Chrome, trip_type: TripType) -> Dict:
        """Extract Overland flight results"""
        try:
            results = {}

            # Extract departure flights
            departure_flights = self._extract_overland_flights_table(driver, "outboundFlightListContainer", "departure")
            if departure_flights[0].get("flight_number") != "":
                results['departure'] = departure_flights

            # Extract return flights for round trips
            if trip_type == TripType.ROUND_TRIP:
                return_flights = self._extract_overland_flights_table(driver, "inboundFlightListContainer", "return")
                if return_flights[0].get("flight_number") != "":
                    results['return'] = return_flights

            return results if results else None

        except Exception as e:
            self.logger.error(f"Error extracting Overland results: {e}")
            return None

    def _extract_overland_flights_table(self, driver: webdriver.Chrome, table_id: str, label: str) -> List[Dict]:
        """Extract flights from Overland table"""
        try:
            table = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, table_id))
            )

            flights = table.find_elements(By.CLASS_NAME, "flightItemNew")
            flight_list = []

            for flight in flights:
                try:
                    flight_data = {
                        "flight_number": None,
                        "departure": {
                            "time": None,
                            "city": None,
                            "date": None
                        },
                        "arrival": {
                            "time": None,
                            "city": None,
                            "date": None
                        },
                        "duration": None,
                        "type": None,
                        "price": None,
                        "status": None,
                        "fares": []
                    }
                    # Extract flight number and airline
                    try:
                        title_right = flight.find_element(By.CLASS_NAME, "flightItem_titleRight")
                        flight_data["flight_number"] = title_right.find_element(By.TAG_NAME, "strong").text.strip()
                    except:
                        pass

                    # Extract departure info
                    try:
                        title_left = flight.find_element(By.CLASS_NAME, "flightItem_titleLeft")
                        depart_time = title_left.find_elements(By.CLASS_NAME, "flightItem_titleTime")[0]
                        flight_data["departure"]["time"] = depart_time.find_element(By.TAG_NAME, "strong").text.strip()
                        depart_info = depart_time.find_element(By.TAG_NAME, "span").text.strip()
                        depart_date, depart_city = depart_info.split("|")
                        flight_data["departure"]["date"] = depart_date.strip()
                        flight_data["departure"]["city"] = depart_city.strip()
                    except:
                        pass

                    # Extract arrival info
                    try:
                        title_left = flight.find_element(By.CLASS_NAME, "flightItem_titleLeft")
                        arrive_time = title_left.find_elements(By.CLASS_NAME, "flightItem_titleTime")[1]
                        flight_data["arrival"]["time"] = arrive_time.find_element(By.TAG_NAME, "strong").text.strip()
                        arrive_info = arrive_time.find_element(By.TAG_NAME, "span").text.strip()
                        arrive_date, arrive_city = arrive_info.split("|")
                        flight_data["arrival"]["date"] = arrive_date.strip()
                        flight_data["arrival"]["city"] = arrive_city.strip()
                    except:
                        pass

                    # Extract duration and flight type
                    try:
                        flight_data["duration"] = flight.find_element(By.CLASS_NAME,
                                                                      "flightItem__duration").text.strip()
                        flight_data["type"] = flight.find_element(By.CLASS_NAME,
                                                                  "flightChoice_tooltipToggle").text.strip()
                    except:
                        pass

                    # Extract status and price
                    try:
                        status_element = flight.find_element(By.CLASS_NAME, "flightBlockSelect")
                        status_text = status_element.text.strip()

                        if "SOLD OUT" in status_text:
                            flight_data["status"] = "NOT_AVAILABLE"
                            flight_data["price"] = None
                        else:
                            try:
                                price_element = flight.find_element(By.CLASS_NAME, "minPrice")
                                flight_data["price"] = price_element.text.strip()
                                flight_data["status"] = "AVAILABLE"
                            except:
                                flight_data["status"] = "PRICE_NOT_AVAILABLE"
                                flight_data["price"] = None
                    except:
                        flight_data["status"] = "UNKNOWN"
                        flight_data["price"] = None

                    # Extract fare details if available
                    if flight_data["status"] == "AVAILABLE":
                        try:
                            expand_button = flight.find_element(By.CLASS_NAME, "js-flightItem_titleBtn__btn")
                            driver.execute_script("arguments[0].click();", expand_button)
                            wait(3, 4)

                            container_id = expand_button.get_attribute("aria-controls")
                            fare_container = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.ID, container_id))
                            )

                            fare_boxes = fare_container.find_elements(By.CLASS_NAME, "flight-class__box")
                            for fare in fare_boxes:
                                if not fare.get_attribute("data-bookable") == "true":
                                    continue

                                try:
                                    fare_data = {
                                        "type": fare.get_attribute("data-classname"),
                                        "price": fare.find_element(By.CLASS_NAME, "btn-class").text.strip(),
                                    }
                                    flight_data["fares"].append(fare_data)
                                except:
                                    continue
                        except:
                            pass

                    flight_list.append(flight_data)
                except:
                    continue

            return flight_list

        except Exception as e:
            self.logger.error(f"Error extracting Overland flights table: {e}")
            return []


class SearchAirLineView(APIView):
    """Optimized Django view for concurrent airline search"""

    def __init__(self):
        super().__init__()
        self.scraper = ConcurrentAirlineScraper(max_workers=9)  # Optimized for 9 airlines
        self.logger = logging.getLogger(__name__)

    def get(self, request):
        # Get airline parameter from query params
        airline = request.query_params.get('airline', None)
        
        # Create search config from query parameters
        search_config = self._create_search_config(request.query_params)
        if not search_config:
            return Response({"error": "Invalid search parameters"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Perform search with optional airline filter
            results = self.scraper.search_all_airlines(search_config, airline)
            formatted_results = self._format_search_results(results, search_config)
            return Response(formatted_results)
        except Exception as e:
            self.logger.error(f"Error in GET request: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        # Get airline parameter from request data
        airline = request.data.get('airline', None)
        
        try:
            results = self._perform_search(request)
            return Response(results)
        except Exception as e:
            self.logger.error(f"Error in POST request: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _perform_search(self, request):
        search_config = self._create_search_config(request.data)
        if not search_config:
            raise ValueError("Invalid search parameters")

        # Get airline parameter from request data
        airline = request.data.get('airline', None)
        
        # Perform search with optional airline filter
        results = self.scraper.search_all_airlines(search_config, airline)
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

    def _format_search_results(self, raw_results: Dict, search_config: FlightSearchConfig) -> Dict:
        """Format search results for API response"""
        try:
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


def index(request):
    return HttpResponse('Welcome to AeroFinder Server API Page')
