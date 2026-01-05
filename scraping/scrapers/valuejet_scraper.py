import logging
import random
import re
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


class ValueJetScraper:
    """Scraper for ValueJet Airways"""

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
        
        # Build requestInfo parameter (single quotes need to be encoded as %27)
        if search_config.trip_type == TripType.ONE_WAY:
            # One-way: till is empty
            request_info = f"dep:'{dep_port}',arr:'{arr_port}',on:'{dep_date}',till:'',p.a:{search_config.adults},p.c:{search_config.children},p.i:{search_config.infants}"
        else:
            # Round-trip: include return date
            ret_date = self._convert_date_format(search_config.return_date)
            request_info = f"dep:'{dep_port}',arr:'{arr_port}',on:'{dep_date}',till:'{ret_date}',p.a:{search_config.adults},p.c:{search_config.children},p.i:{search_config.infants}"
        
        # URL encode the requestInfo (single quotes become %27)
        from urllib.parse import quote
        encoded_request_info = quote(request_info, safe='')
        
        return f"{base_url}/flight-result?requestInfo={encoded_request_info}"
    
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
        """Scrape ValueJet Airways flights"""
        try:
            self.logger.info(f"🔍 Searching {airline_config.name}...")
            
            # Build and navigate directly to results URL
            results_url = self._build_results_url(airline_config, search_config)
            self.logger.info(f"🌐 Navigating to: {results_url}")
            driver.get(results_url)
            
            # Additional wait to ensure all content is loaded
            # wait(3, 4)

            # Extract results
            return self.extract_results(driver, search_config.trip_type)

        except Exception as e:
            self.logger.error(f"ValueJet scraping error: {e}")
            return None

    def extract_results(self, driver: webdriver.Chrome, trip_type: TripType) -> Dict:
        """Extract ValueJet flight results"""
        try:
            results = {}
            
            # Extract departure flights
            print("[+] Extracting departure flights...")
            try:
                outbound_container = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "outbound"))
                )
                
                flight_details = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.flex.flex-col.w-full.border.border-gray-200.rounded-lg.lg\\:pb-4.mb-4"))
                )
                
                if not flight_details:
                    self.logger.warning("Flight details not found in outbound container")
                    return None
                    
                departure_flights = self._extract_flights_table(driver, outbound_container, "departure")
                if departure_flights is None:
                    return None
                results['departure'] = departure_flights

                # Extract return flights if round trip
                if trip_type == TripType.ROUND_TRIP:
                    print("[+] Extracting return flights...")
                    inbound_container = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "inbound"))
                    )
                    
                    return_flights = self._extract_flights_table(driver, inbound_container, "return")
                    if return_flights is None:
                        return None
                    results['return'] = return_flights

                return results

            except Exception as e:
                self.logger.error(f"Error extracting ValueJet flight information: {e}")
                return None

        except Exception as e:
            self.logger.error(f"Error in ValueJet results extraction: {e}")
            return None

    def _extract_flights_table(self, driver, container, label: str) -> List[Dict]:
        """Extract flights from ValueJet table with ThreadPool"""
        try:
            flight_items = container.find_elements(By.CSS_SELECTOR, "div.flex.flex-col.w-full.border.border-gray-200.rounded-lg")
            if not flight_items:
                self.logger.warning(f"No flight items found for {label}")
                return []

            all_flights_data = []
            panel_htmls_to_parse = []

            # 1. Iterate through flights, extract basic info, click for fares, and collect panel HTML
            for idx, flight_element in enumerate(flight_items):
                flight_data = {
                    'flight_number': None,
                    'departure': {'time': None},
                    'arrival': {'time': None},
                    'fares': []
                }
                
                # Use BeautifulSoup for reliable text extraction
                flight_html = flight_element.get_attribute('outerHTML')
                soup = BeautifulSoup(flight_html, 'html.parser')

                # Extract departure and arrival info
                dep_info = soup.select_one("span.flex.basis-1.flex-col.pb-1")
                arr_info = soup.select_one("span.flex.basis-1.flex-col.items-end.pb-1")

                if dep_info:
                    dep_time = dep_info.select_one("span.text-primary.text-2xl.font-semibold").get_text(strip=True)
                    dep_ampm = dep_info.select_one("span.text-sm.font-semibold").get_text(strip=True)
                    flight_data['departure']['time'] = f"{dep_time} {dep_ampm}"

                if arr_info:
                    arr_time = arr_info.select_one("span.text-primary.text-2xl.font-semibold").get_text(strip=True)
                    arr_ampm = arr_info.select_one("span.text-sm.font-semibold").get_text(strip=True)
                    flight_data['arrival']['time'] = f"{arr_time} {arr_ampm}"

                # Extract flight number and duration
                flight_details = soup.select_one("div.font-roboto.flex.flex-col.basis-3")
                flight_number = None
                if flight_details:
                    # Try to find a p tag that looks like a flight number (e.g., VJ1234)
                    for p in flight_details.find_all('p'):
                        text = p.get_text(strip=True)
                        if re.match(r'^[A-Z]{2,3}\d{2,4}$', text):
                            flight_number = text
                            break
                    # Fallback: use the first p tag if nothing matches
                    if not flight_number and flight_details.find_all('p'):
                        flight_number = flight_details.find_all('p')[0].get_text(strip=True)
                flight_data['flight_number'] = flight_number

                # Click to reveal fares and collect HTML for parsing
                try:
                    all_buttons = flight_element.find_elements(By.TAG_NAME, "button")
                    
                    fare_button = None
                    button_selectors = [
                        "button.bg-primary.text-white.font-black.font-roboto.w-full.text-xl.capitalize",
                        "button.bg-primary.text-white",
                        "button[class*='bg-primary'][class*='text-white']",
                    ]
                    
                    for selector in button_selectors:
                        try:
                            fare_button = flight_element.find_element(By.CSS_SELECTOR, selector)
                            break
                        except:
                            continue
                    
                    if fare_button is None:
                        for button in all_buttons:
                            try:
                                button_text = button.text
                                if '₦' in button_text and 'Starting at' in flight_element.text:
                                    fare_button = button
                                    break
                            except:
                                continue
                    
                    if fare_button is None:
                        panel_htmls_to_parse.append((idx, ''))
                        continue
                    
                    driver.execute_script("arguments[0].click();", fare_button)
                    wait(1, 2)
                    
                    fare_panel = None
                    selectors_to_try = [
                        "div.p-accordion-content",
                        "div[role='region']",
                        "div.chakra-collapse",
                        "div.chakra-accordion__panel",
                        "div.grid.grid-cols-6",
                        "div.flex.flex-col.gap-4"
                    ]
                    
                    for selector in selectors_to_try:
                        try:
                            fare_panel = flight_element.find_element(By.CSS_SELECTOR, selector)
                            break
                        except:
                            continue
                    
                    if fare_panel is None:
                        panel_htmls_to_parse.append((idx, ''))
                        continue
                    
                    panel_html = fare_panel.get_attribute('outerHTML')
                    panel_htmls_to_parse.append((idx, panel_html))

                except Exception as e:
                    self.logger.warning(f"Could not click fare button for flight {idx}: {e}")
                    panel_htmls_to_parse.append((idx, ''))

                all_flights_data.append(flight_data)

            # 2. Parse all collected fare panels in parallel
            with ThreadPoolExecutor() as executor:
                future_to_idx = {executor.submit(self._parse_fares, html): idx for idx, html in panel_htmls_to_parse}
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        fares = future.result()
                        formatted_fares = []
                        for fare in fares:
                            if 'name' in fare and 'price' in fare:
                                formatted_fares.append({'type': fare['name'], 'price': fare['price']})
                        all_flights_data[idx]['fares'] = formatted_fares
                    except Exception as exc:
                        self.logger.warning(f'Flight {idx} generated an exception during fare parsing: {exc}')
                        all_flights_data[idx]['fares'] = []

            return all_flights_data

        except Exception as e:
            self.logger.error(f"Error in extract_valuejet_flights_table for {label}: {e}")
            return []

    def _parse_fares(self, panel_html):
        """Parse fare name and price from ValueJet fare panel HTML"""
        soup = BeautifulSoup(panel_html, 'html.parser')
        fares = []
        if not panel_html:
            return fares
        
        fare_buttons = soup.select("div.grid.grid-cols-6 > button")
        for btn in fare_buttons:
            fare_name_tag = btn.select_one("span.text-header")
            price_tag = btn.select_one("h5.text-lg.text-primary.font-bold")
            
            if fare_name_tag and price_tag:
                fare_name = fare_name_tag.get_text(strip=True)
                price_text = price_tag.get_text(strip=True)
                
                price = "Sold Out" if "Sold Out" in price_text else price_text
                fares.append({"name": fare_name, "price": price})
        return fares

