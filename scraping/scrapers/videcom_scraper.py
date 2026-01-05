import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from twocaptcha import TwoCaptcha

from ..airline_config import FlightSearchConfig, TripType
from .utils import extract_airport_code


def wait(min_time=2, max_time=4):
    """Wait for a random time between min_time and max_time"""
    time.sleep(random.uniform(min_time, max_time))


class VidecomScraper:
    """Scraper for Videcom based airlines"""

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)

    def scrape(self, driver: webdriver.Chrome, airline_config, search_config: FlightSearchConfig) -> Optional[Dict]:
        """Optimized Videcom scraping"""
        try:
            self.logger.info(f"🔍 Searching {airline_config.name}...")
            driver.get(airline_config.url)

            # Wait for form elements
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "Origin"))
            )

            # Fill form efficiently
            self.fill_form(driver, search_config, airline_config.key)

            # Submit and wait for results
            self.submit_search(driver)

            # Extract results
            return self.extract_results(driver, search_config.trip_type, airline_config.key)

        except Exception as e:
            self.logger.error(f"Videcom scraping error for {airline_config.name}: {e}")
            return None

    def fill_form(self, driver: webdriver.Chrome, config: FlightSearchConfig, airline_name: str):
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
                wait(1, 2)

            departure_city = extract_airport_code(config.departure_city)
            return_city = extract_airport_code(config.arrival_city)

            dep_js_script = f"""
                function extractAirportCode(text) {{
                    const matches = [...text.matchAll(/\\(([^)]+)\\)/g)];
                    if (matches.length > 0) {{
                        return matches[matches.length - 1][1].toUpperCase();
                    }}
                    return '';
                }}

                var originSelect = document.getElementById('Origin');
                if (originSelect) {{
                    const options = Array.from(originSelect.options);
                    const matchingOption = options.find(option =>
                        extractAirportCode(option.textContent) == '{departure_city}'
                    );
                    if (matchingOption) {{
                        originSelect.value = matchingOption.value;
                        originSelect.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}
                return false;
            """

            driver.execute_script(dep_js_script)
            time.sleep(1)

            script = f"""
                // Set cities
                function extractAirportCode(text) {{
                    const matches = [...text.matchAll(/\\(([^)]+)\\)/g)];
                    if (matches.length > 0) {{
                        return matches[matches.length - 1][1].toUpperCase();
                    }}
                    return '';
                }}

                var destSelect = document.getElementById('Destination');
                if (destSelect) {{
                    const options = Array.from(destSelect.options);
                    const matchingOption = options.find(option =>
                        extractAirportCode(option.textContent) == '{return_city}'
                    );
                    if (matchingOption) {{
                        destSelect.value = matchingOption.value;
                        destSelect.dispatchEvent(new Event('change', {{ bubbles: true }}));
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
            time.sleep(1)

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

    def submit_search(self, driver: webdriver.Chrome):
        """Submit Videcom search form and handle reCAPTCHA if present"""
        # try:
            # Click the submit button
        submit_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "submitButton"))
        )
        submit_button.click()

        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.ID, "calView_0"))
        )

        print('submitButton')

            # Check if reCAPTCHA is present
        #     try:
        #         # Wait for either reCAPTCHA or results with a short timeout
        #         WebDriverWait(driver, 3).until(
        #             lambda d: d.find_elements(By.CLASS_NAME, "g-recaptcha") or d.find_elements(By.ID, "calView_0")
        #         )
        #
        #         # If reCAPTCHA is present, handle it
        #         if driver.find_elements(By.CLASS_NAME, "g-recaptcha"):
        #             recaptcha_element = driver.find_element(By.CLASS_NAME, "g-recaptcha")
        #             sitekey = recaptcha_element.get_attribute("data-sitekey")
        #             self.logger.info(f"Found reCAPTCHA with sitekey: {sitekey}")
        #
        #             # Get current URL for captcha solving
        #             current_url = driver.current_url
        #
        #             # Solve the captcha using 2Captcha
        #             solver = TwoCaptcha(os.getenv("CAPCHA_KEY"))
        #             try:
        #                 result = solver.recaptcha(
        #                     sitekey=sitekey,
        #                     url=current_url
        #                 )
        #
        #                 if result and 'code' in result:
        #                     # Insert the solved captcha token
        #                     token = result['code']
        #                     self.logger.info("Successfully solved reCAPTCHA")
        #
        #                     # Execute JavaScript to set the token
        #                     driver.execute_script(f"""
        #                         document.querySelector('[id="g-recaptcha-response"]').innerText = '{token}';
        #                     """)
        #
        #                     # Trigger the callback function
        #                     driver.execute_script("recaptchaCallback(arguments[0]);", token)
        #
        #                     # Wait for results after captcha submission
        #                     # WebDriverWait(driver, 2).until(
        #                     #     EC.presence_of_element_located((By.ID, "calView_0"))
        #                     # )
        #                     # time.sleep(1)
        #                 else:
        #                     raise Exception("Failed to get captcha solution")
        #
        #             except Exception as e:
        #                 self.logger.error(f"Error solving reCAPTCHA: {str(e)}")
        #                 raise
        #         # else:
        #         #     # No reCAPTCHA found, just wait for results
        #         #     self.logger.info("No reCAPTCHA found, proceeding with search")
        #             # WebDriverWait(driver, 2).until(
        #             #     EC.presence_of_element_located((By.ID, "calView_0"))
        #             # )
        #             # time.sleep(1)
        #
        #     except Exception as e:
        #         self.logger.error(f"Error handling search submission: {str(e)}")
        #         raise
        #
        #     print('done')
        #
        # except Exception as e:
        #     self.logger.error(f"Error submitting Videcom search: {e}")
        #     raise

    def extract_results(self, driver: webdriver.Chrome, trip_type: TripType, airline_name: str) -> Dict:
        """Optimized Videcom results extraction"""
        try:
            results = {}

            # Extract departure flights
            departure_flights = self._extract_flights_table(driver, "calView_0")
            if departure_flights:
                results['departure'] = departure_flights

            # Extract return flights for round trips
            if trip_type == TripType.ROUND_TRIP:
                return_flights = self._extract_flights_table(driver, "calView_1")
                if return_flights:
                    results['return'] = return_flights

            return results if results else None

        except Exception as e:
            self.logger.error(f"Error extracting Videcom results: {e}")
            return None

    def _extract_flights_table(self, driver: webdriver.Chrome, table_id: str) -> List[Dict]:
        """Extract flights from table using BeautifulSoup and parallel processing"""
        try:
            # Wait for table to be present
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, table_id))
            )

            # Get the table HTML
            table_html = driver.find_element(By.ID, table_id).get_attribute('outerHTML')
            soup = BeautifulSoup(table_html, 'html.parser')

            # Find all flight elements
            flight_elements = soup.select(".flt-panel")

            def process_flight(flight_element):
                try:
                    return self._extract_flight_data(flight_element)
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

    def _extract_flight_data(self, flight_element) -> Optional[Dict]:
        """Extract Videcom flight data using BeautifulSoup"""
        try:
            flight_data = {
                "flight_number": self._safe_extract_text_bs(flight_element, ".flightnumber"),
                "departure": {
                    "time": self._safe_extract_text_bs(flight_element, ".cal-Depart-time .time"),
                },
                "arrival": {
                    "time": self._safe_extract_text_bs(flight_element, ".cal-Arrive-time .time"),
                },
                "fares": []
            }

            def process_fare(panel_num):
                try:
                    fare_element = flight_element.select_one(f".classband-panel-{panel_num}")
                    if not fare_element:
                        return None

                    price = self._safe_extract_text_bs(fare_element, ".FareClass-price")
                    if price:
                        return {
                            "type": fare_element.get("data-classband") or f"Class_{panel_num}",
                            "price": price
                        }
                except Exception as e:
                    self.logger.warning(f"Error processing fare panel {panel_num}: {e}")
                    return None

            # Process fare panels in parallel
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(process_fare, i) for i in range(1, 5)]
                fares = [result for result in (f.result() for f in as_completed(futures)) if result]

            flight_data["fares"] = fares
            return flight_data if flight_data.get("flight_number") else None

        except Exception as e:
            self.logger.error(f"Error extracting Videcom flight data: {e}")
            return None

    def _safe_extract_text_bs(self, element, selector: str) -> Optional[str]:
        """Safely extract text from BeautifulSoup element using CSS selector"""
        try:
            found_element = element.select_one(selector)
            return found_element.text.strip() if found_element else None
        except Exception as e:
            self.logger.warning(f"Error extracting text with selector {selector}: {e}")
            return None

