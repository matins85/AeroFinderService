import logging
import random
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


def wait(min_time=2, max_time=4):
    """Wait for a random time between min_time and max_time"""
    time.sleep(random.uniform(min_time, max_time))


class GreenAfricaScraper:
    """Scraper for Green Africa Airways"""

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
        
        # Build query parameters
        params = [
            f'origin={dep_port}',
            f'destination={arr_port}',
            f'departure={dep_date}',
            f'adt={search_config.adults}',
            f'chd={search_config.children}',
            f'inf={search_config.infants}',
            'promocode='
        ]
        
        # Add return date and round trip flag for round trips
        if search_config.trip_type == TripType.ROUND_TRIP:
            ret_date = self._convert_date_format(search_config.return_date)
            params.insert(3, f'return={ret_date}')
            params.insert(4, 'round=1')
        
        query_string = '&'.join(params)
        return f"{base_url}/booking/select?{query_string}"
    
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
        """Scrape Green Africa Airways flights"""
        try:
            self.logger.info(f"🔍 Searching {airline_config.name}...")
            
            # Build and navigate directly to results URL
            results_url = self._build_results_url(airline_config, search_config)
            self.logger.info(f"🌐 Navigating to: {results_url}")
            driver.get(results_url)

            # Wait for results to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "bookings-container"))
            )
            
            # Additional wait to ensure all content is loaded
            # wait(3, 4)

            # Extract results
            return self.extract_results(driver, search_config.trip_type)

        except Exception as e:
            self.logger.error(f"Green Africa scraping error: {e}")
            return None

    def extract_results(self, driver: webdriver.Chrome, trip_type: TripType) -> Dict:
        """Extract Green Africa flight results"""
        try:
            results = {}
            
            # Extract departure flights
            print("[+] Extracting departure flights...")
            try:
                # Find all booking containers with the exact class
                booking_containers = WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.flex.flex-col.gap-16.mt-12.w-full.bookings-container"))
                )
                # First container should be departure flights
                if booking_containers:
                    departure_flights = self._extract_flights_table(driver, booking_containers[0], "departure")
                    if departure_flights:
                        results['departure'] = departure_flights
            except Exception as e:
                self.logger.error(f"Error extracting departure flights: {e}")
                
            # Extract return flights if present
            print("[+] Extracting return flights...")
            try:
                if len(booking_containers) > 1:
                    return_flights = self._extract_flights_table(driver, booking_containers[1], "return")
                    if return_flights:
                        results['return'] = return_flights
            except Exception as e:
                self.logger.error(f"Error extracting return flights: {e}")
                
            return results if results else None

        except Exception as e:
            self.logger.error(f"Error in Green Africa results extraction: {e}")
            return None

    def _extract_flights_table(self, driver, container, label: str) -> List[Dict]:
        """Extract flights from Green Africa table with ThreadPool"""
        try:
            flight_containers = container.find_elements(By.CSS_SELECTOR, ".chakra-accordion__item")
            if not flight_containers:
                self.logger.warning(f"No flight containers found for {label}")
                return []

            panel_htmls = []
            flight_infos = []

            # 1. Click all Select buttons and collect panel HTMLs
            for idx, flight in enumerate(flight_containers):
                flight_info = {
                    'flight_number': None,
                    'departure': {'time': None},
                    'arrival': {'time': None},
                    'fares': []
                }
                try:
                    # Parse summary info with BeautifulSoup
                    flight_html = flight.get_attribute('outerHTML')
                    soup = BeautifulSoup(flight_html, 'html.parser')
                    times = soup.select('h3.text-h4, h3.lg\\:text-\\[30px\\]')
                    airports = soup.select('p.text-sm.lg\\:text-p')
                    if len(times) >= 2 and len(airports) >= 2:
                        flight_info['departure']['time'] = times[0].get_text(strip=True)
                        flight_info['arrival']['time'] = times[1].get_text(strip=True)
                    # Flight number and type
                    try:
                        flight_no = soup.find('p', string=lambda t: t and 'Flight no.' in t)
                        if flight_no:
                            flight_info['flight_number'] = flight_no.find_next('p').get_text(strip=True)
                        else:
                            flight_info['flight_number'] = None
                    except:
                        flight_info['flight_number'] = None

                    # Click the Select button
                    try:
                        select_btn = flight.find_element(By.CSS_SELECTOR, ".chakra-accordion__button")
                        try:
                            select_btn.click()
                        except Exception as e:
                            self.logger.warning(f"Native click failed for flight {idx}: {e}, trying JS click")
                            driver.execute_script("arguments[0].click();", select_btn)
                        time.sleep(0.5)
                    except Exception as e:
                        self.logger.warning(f"Could not click Select button for flight {idx}: {e}")
                        continue

                    # Get panel HTML
                    try:
                        panel = WebDriverWait(flight, 3).until(
                            lambda d: flight.find_element(By.CSS_SELECTOR, ".chakra-accordion__panel")
                        )
                        panel_html = panel.get_attribute('outerHTML')
                        panel_htmls.append((idx, panel_html))
                        flight_infos.append(flight_info)
                    except Exception as e:
                        self.logger.warning(f"Error extracting fares for flight {idx}: {e}")
                        continue

                except Exception as e:
                    self.logger.warning(f"Error extracting flight {idx}: {e}")
                    continue

            # 2. Parse all fare panels in parallel using ThreadPool
            with ThreadPoolExecutor() as executor:
                future_to_idx = {executor.submit(self._parse_fares, html): idx for idx, html in panel_htmls}
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        fares = future.result()
                        # Convert fares to the correct format: type/price
                        formatted_fares = []
                        for fare in fares:
                            if 'name' in fare and 'price' in fare:
                                formatted_fares.append({'type': fare['name'], 'price': fare['price']})
                        flight_infos[idx]['fares'] = formatted_fares
                    except Exception as e:
                        self.logger.warning(f"Error in ThreadPool fare parsing for flight {idx}: {e}")
                        flight_infos[idx]['fares'] = []

            return flight_infos

        except Exception as e:
            self.logger.error(f"Error in extract_greenafrica_flights_table for {label}: {e}")
            return []

    def _parse_fares(self, panel_html):
        """Parse fare name and price from Green Africa fare panel HTML"""
        soup = BeautifulSoup(panel_html, "html.parser")
        fares = []

        # Use CSS selector for partial class match (robust to class order)
        desktop_panel = soup.select_one("div.hidden.lg\\:grid")
        if not desktop_panel:
            self.logger.warning("No desktop panel found!")
            return fares

        for fare_div in desktop_panel.find_all("div", class_="box-shadow"):
            name_tag = fare_div.find("h4", class_="text-h4")
            price_btn = fare_div.find("button", class_="border-brand_blue")
            price_tag = price_btn.find("span", class_="notranslate") if price_btn else None
            if name_tag and price_tag:
                fares.append({
                    "name": name_tag.get_text(strip=True),
                    "price": price_tag.get_text(strip=True)
                })
        return fares

