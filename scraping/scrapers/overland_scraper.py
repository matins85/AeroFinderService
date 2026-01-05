import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from twocaptcha import TwoCaptcha
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..airline_config import FlightSearchConfig, TripType
from .utils import extract_airport_code


def wait(min_time=2, max_time=4):
    """Wait for a random time between min_time and max_time"""
    time.sleep(random.uniform(min_time, max_time))


class OverlandScraper:
    """Scraper for Overland Airways"""

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)

    def _build_results_url(self, airline_config, search_config: FlightSearchConfig) -> str:
        """Build the results URL with query parameters"""
        base_url = airline_config.url.rstrip('/')
        
        # Extract airport codes
        dep_port = extract_airport_code(search_config.departure_city)
        arr_port = extract_airport_code(search_config.arrival_city)
        
        # Convert date format from "06 Jun 2025" to "2025-12-06"
        dep_date = self._convert_date_format(search_config.departure_date)
        
        # Build URL path
        if search_config.trip_type == TripType.ONE_WAY:
            # One-way format: /flight-results/ABV-LOS/2025-12-11/NA/1/0/0
            url = f"{base_url}/flight-results/{dep_port}-{arr_port}/{dep_date}/NA/{search_config.adults}/{search_config.children}/{search_config.infants}"
        else:
            # Round-trip format: /flight-results/ABV-LOS/2025-12-12/2026-01-08/1/0/0
            ret_date = self._convert_date_format(search_config.return_date)
            url = f"{base_url}/flight-results/{dep_port}-{arr_port}/{dep_date}/{ret_date}/{search_config.adults}/{search_config.children}/{search_config.infants}"
        
        return url
    
    def _convert_date_format(self, date_str: str) -> str:
        """Convert date from 'dd MMM yyyy' to 'yyyy-MM-dd'"""
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
            
            return f"{year}-{month}-{day.zfill(2)}"
        except Exception as e:
            self.logger.error(f"Error converting date format: {e}")
            return date_str

    def scrape(self, driver: webdriver.Chrome, airline_config, search_config: FlightSearchConfig) -> Optional[Dict]:
        """Scrape Overland Airways flights"""
        try:
            # Build and navigate directly to results URL
            results_url = self._build_results_url(airline_config, search_config)
            self.logger.info(f"🌐 Navigating to: {results_url}")
            driver.get(results_url)

            print('submitButton')

            # Check if reCAPTCHA is present
            # try:
            #     # Wait for either reCAPTCHA or results with a short timeout
            #     WebDriverWait(driver, 10).until(
            #         lambda d: d.find_elements(By.CLASS_NAME, "g-recaptcha")
            #     )
            #
            #     # If reCAPTCHA is present, handle it
            #     if driver.find_elements(By.CLASS_NAME, "g-recaptcha"):
            #         print('capcha detected')
            #         recaptcha_element = driver.find_element(By.CLASS_NAME, "g-recaptcha")
            #         sitekey = recaptcha_element.get_attribute("data-sitekey")
            #         self.logger.info(f"Found reCAPTCHA with sitekey: {sitekey}")
            #
            #         # Get current URL for captcha solving
            #         current_url = driver.current_url
            #
            #         # Solve the captcha using 2Captcha
            #         solver = TwoCaptcha(os.getenv("CAPCHA_KEY"))
            #         try:
            #             result = solver.recaptcha(
            #                 sitekey=sitekey,
            #                 url=current_url
            #             )
            #
            #             if result and 'code' in result:
            #                 # Insert the solved captcha token
            #                 token = result['code']
            #                 self.logger.info("Successfully solved reCAPTCHA")
            #
            #                 # Execute JavaScript to set the token
            #                 driver.execute_script(f"""
            #                                 document.querySelector('[id="g-recaptcha-response"]').innerText = '{token}';
            #                             """)
            #
            #                 # Trigger the callback function
            #                 driver.execute_script("recaptchaCallback(arguments[0]);", token)
            #
            #                 # Wait for results after captcha submission
            #                 # WebDriverWait(driver, 2).until(
            #                 #     EC.presence_of_element_located((By.ID, "calView_0"))
            #                 # )
            #                 # time.sleep(1)
            #             else:
            #                 raise Exception("Failed to get captcha solution")
            #
            #         except Exception as e:
            #             self.logger.error(f"Error solving reCAPTCHA: {str(e)}")
            #             raise
            #
            # except Exception as e:
            #     self.logger.error(f"Error handling search submission: {str(e)}")
            #     raise

            print('done')

            # Wait for results to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "flightItem"))
            )
            # time.sleep(3)

            # Extract results
            return self.extract_results(driver, search_config.trip_type)

        except Exception as e:
            self.logger.error(f"Overland scraping error: {e}")
            return None

    def extract_results(self, driver: webdriver.Chrome, trip_type: TripType) -> Dict:
        """Extract Overland flight results"""
        try:
            results = {}

            # Extract departure flights
            departure_flights = self._extract_flights_table(driver, "outboundFlightListContainer", "departure")
            if departure_flights and len(departure_flights) > 0 and departure_flights[0].get("flight_number") != "":
                results['departure'] = departure_flights

            # Extract return flights for round trips
            if trip_type == TripType.ROUND_TRIP:
                return_flights = self._extract_flights_table(driver, "inboundFlightListContainer", "return")
                if return_flights and len(return_flights) > 0 and return_flights[0].get("flight_number") != "":
                    results['return'] = return_flights

            return results if results else None

        except Exception as e:
            self.logger.error(f"Error extracting Overland results: {e}")
            return None

    def _extract_flights_table(self, driver, table_id: str, label: str) -> List[Dict]:
        """Extract flights from Overland table with Selenium, BeautifulSoup, and concurrency"""
        try:
            table = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, table_id))
            )

            flights = table.find_elements(By.CLASS_NAME, "flightItemNew")
            flight_list = []

            def process_flight(flight):
                try:
                    flight_data = {
                        "flight_number": None,
                        "departure": {"time": None},
                        "arrival": {"time": None},
                        "price": None,
                        "fares": []
                    }

                    # Use BeautifulSoup to parse the flight block
                    soup = BeautifulSoup(flight.get_attribute("outerHTML"), "html.parser")

                    # Flight number
                    title_right = soup.select_one(".flightItem_titleRight strong")
                    if title_right:
                        flight_data["flight_number"] = title_right.text.strip()

                    # Departure
                    try:
                        depart_block = soup.select(".flightItem_titleLeft .flightItem_titleTime")[0]
                        flight_data["departure"]["time"] = depart_block.select_one("strong").text.strip()
                    except:
                        pass

                    # Arrival
                    try:
                        arrive_block = soup.select(".flightItem_titleLeft .flightItem_titleTime")[1]
                        flight_data["arrival"]["time"] = arrive_block.select_one("strong").text.strip()
                    except:
                        pass

                    # Status and price
                    status_block = soup.select_one(".flightBlockSelect")
                    status_text = status_block.text.strip() if status_block else ""
                    if "SOLD OUT" in status_text:
                        flight_data["status"] = "NOT_AVAILABLE"
                        flight_data["price"] = None
                    else:
                        price_el = soup.select_one(".minPrice")
                        if price_el:
                            flight_data["price"] = price_el.text.strip()
                            flight_data["status"] = "AVAILABLE"
                        else:
                            flight_data["status"] = "PRICE_NOT_AVAILABLE"

                    # Fares if available
                    if flight_data["status"] == "AVAILABLE":
                        try:
                            expand_button = flight.find_element(By.CLASS_NAME, "js-flightItem_titleBtn__btn")
                            driver.execute_script("arguments[0].click();", expand_button)
                            wait(1, 2)

                            container_id = expand_button.get_attribute("aria-controls")
                            fare_container = WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.ID, container_id))
                            )

                            fare_html = fare_container.get_attribute("outerHTML")
                            fare_soup = BeautifulSoup(fare_html, "html.parser")

                            fare_boxes = fare_soup.select(".flight-class__box[data-bookable='true']")
                            for box in fare_boxes:
                                try:
                                    fare_data = {
                                        "type": box.get("data-classname"),
                                        "price": box.select_one(".btn-class").text.strip()
                                    }
                                    flight_data["fares"].append(fare_data)
                                except:
                                    continue
                        except Exception as fe:
                            self.logger.warning(f"⚠️ Fare extraction failed: {fe}")

                    return flight_data
                except Exception as e:
                    self.logger.warning(f"❌ Error processing flight: {e}")
                    return None

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(process_flight, f) for f in flights]
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        flight_list.append(result)

            return flight_list

        except Exception as e:
            self.logger.error(f"🔥 Error extracting Overland flights table: {e}")
            return []

