import logging
import time
import shutil
import subprocess
import random
import re
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
import os
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from twocaptcha import TwoCaptcha, TimeoutException
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse
import undetected_chromedriver as uc
import tempfile


def extract_airport_code(text):
    match = re.findall(r'\(([^)]+)\)', text)
    if match:
        return match[-1].upper()
    return ''


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

    def __init__(self, headless: bool = True, proxy_ip: str = None):
        self.headless = headless
        self.proxy_ip = proxy_ip
        self.logger = logging.getLogger(__name__)

    def create_proxy_auth_extension(self, proxy_host, proxy_port, proxy_user, proxy_pass):
        """Creates a Chrome extension for proxy authentication"""
        manifest_json = {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Proxy Auth Extension",
            "permissions": [
                "proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"
            ],
            "background": {
                "scripts": ["background.js"]
            }
        }

        background_js = f"""
        var config = {{
            mode: "fixed_servers",
            rules: {{
                singleProxy: {{
                    scheme: "http",
                    host: "{proxy_host}",
                    port: parseInt({proxy_port})
                }},
                bypassList: ["localhost"]
            }}
        }};

        chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

        chrome.webRequest.onAuthRequired.addListener(
            function(details) {{
                return {{
                    authCredentials: {{
                        username: "{proxy_user}",
                        password: "{proxy_pass}"
                    }}
                }};
            }},
            {{urls: ["<all_urls>"]}},
            ["blocking"]
        );
        """

        pluginfile = tempfile.mktemp(suffix='.zip')
        with zipfile.ZipFile(pluginfile, 'w') as zp:
            zp.writestr("manifest.json", json.dumps(manifest_json))
            zp.writestr("background.js", background_js)

        return pluginfile

    def create_driver(self, airline_name: str = None, airline_type: str = None) -> webdriver.Chrome:
        """Create optimized Chrome WebDriver with optional proxy per airline."""
        user_agent = UserAgent()
        # options = uc.ChromeOptions()
        options = Options()

        chrome_binary = os.environ.get("CHROME_BIN")
        if chrome_binary:
            options.binary_location = chrome_binary
            self.logger.info(f"Using CHROME_BIN: {chrome_binary}")

        # Create a temporary user data directory for session isolation
        user_data_dir = tempfile.mkdtemp(prefix='chrome_user_data_')
        self.logger.info(f"Created unique Chrome user data directory: {user_data_dir}")

        chrome_options = [
            f"--user-agent={user_agent.random}",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--window-size=1366,768",
            "--disable-infobars",
            "--lang=en-NG",
            "--ignore-certificate-errors",
            "--allow-running-insecure-content",
            "--disable-extensions",
            "--start-maximized",
            "--disable-plugins",
            "--disable-images",
            "--disable-css",
            "--disable-logging",
            "--disable-dev-tools",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=TranslateUI",
            "--disable-default-apps",
            "--disable-sync",
            f"--user-data-dir={user_data_dir}",
        ]

        # Use proxy only for Air Peace
        if airline_name and (airline_name.lower() == "airpeace" or airline_type == AirlineGroup.VIDECOM) and self.proxy_ip:
            chrome_options.extend([
                "--proxy-server='direct://'",
                "--proxy-bypass-list=*"
            ])
            # username = "TP24838919"
            # password = "hFRWnGOW"
            # host = "208.195.161.231"
            # port = 65095

            # self.logger.info(f"Adding proxy extension for Air Peace")
            # # proxy_extension_path = self.create_proxy_auth_extension(
            # #     proxy_host=host,
            # #     proxy_port=port,
            # #     proxy_user=username,
            # #     proxy_pass=password
            # # )
            # # options.add_extension(proxy_extension_path)
            # proxy = f"http://{username}:{password}@{host}:{port}"
            # chrome_options.extend([
            #     f"--proxy-server={proxy}",
            # ])
            # print("Added proxy extension for Air Peace")

            # self.logger.info(f"Added proxy extension for Air Peace")
        else:
            # Bypass proxy
            chrome_options.extend([
                "--proxy-server='direct://'",
                "--proxy-bypass-list=*"
            ])

        if self.headless:
            chrome_options.extend([
                "--headless=new",
                "--disable-software-rasterizer",
                "--disable-web-security",
            ])

        for opt in chrome_options:
            options.add_argument(opt)

        # Performance preferences
        prefs = {
            "profile.default_content_setting_values": {
                "images": 2,
                "plugins": 2,
                "popups": 2,
                "geolocation": 1,
                "notifications": 2,
                "media_stream": 2,
            },
            "intl.accept_languages": "en-NG,en"
        }
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Path to chromedriver
        # chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
        service = self._create_service()
        try:
            # driver = uc.Chrome(
            #     driver_executable_path=chromedriver_path,
            #     options=options,
            #     headless=self.headless
            # )
            driver = webdriver.Chrome(service=service, options=options)
            self.logger.info("Successfully created Chrome driver")
        except Exception as e:
            self.logger.error(f"Failed to create Chrome driver: {e}")
            shutil.rmtree(user_data_dir, ignore_errors=True)
            raise

        # Set timeouts
        driver.set_page_load_timeout(15)
        driver.implicitly_wait(5)

        # Evade detection
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        # Set location override (e.g., Lagos, Nigeria)
        driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
            "latitude": 6.5244,
            "longitude": 3.3792,
            "accuracy": 100
        })
        driver.execute_script("""
            navigator.geolocation.getCurrentPosition = function(success){
                success({
                    coords: {
                        latitude: 6.5244,
                        longitude: 3.3792,
                        accuracy: 100
                    }
                });
            };
        """)

        return driver


    def _create_service(self):
        """Create Chrome service compatible with Heroku (Chrome for Testing buildpack)"""

        # Option 0: Check Heroku-provided CHROMEDRIVER_PATH
        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
        if chromedriver_path and os.path.exists(chromedriver_path):
            self.logger.info(f"Using CHROMEDRIVER_PATH from env: {chromedriver_path}")
            return Service(chromedriver_path)

        # Option 1: Try system ChromeDriver (installed via brew or apt)
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

        # Option 3: Try webdriver-manager
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()
            if os.access(driver_path, os.X_OK):
                self.logger.info(f"Using webdriver-manager ChromeDriver: {driver_path}")
                return Service(driver_path)
            else:
                self.logger.warning(f"ChromeDriver at {driver_path} is not executable")
        except Exception as e:
            self.logger.warning(f"webdriver-manager failed: {e}")

        # Option 4: Fallback
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


# class OptimizedCloudflareHandler:
#     """Optimized handler for Cloudflare Turnstile CAPTCHA."""
#
#     def __init__(self, api_key: str = None):
#         self.api_key = api_key or os.getenv("CAPCHA_KEY")
#         self.solver = TwoCaptcha(self.api_key)
#         self.logger = logging.getLogger(__name__)
#
#     def handle_protection(self, driver: webdriver.Chrome, max_wait: int = 5) -> bool:
#         """
#         Detect and solve Cloudflare Turnstile challenge if present.
#         Returns True if passed or no challenge found.
#         """
#         try:
#             print("Checking for Cloudflare Turnstile challenge...")
#             WebDriverWait(driver, max_wait).until(
#                 EC.presence_of_element_located((By.NAME, "cf-turnstile-response"))
#             )
#             print("Cloudflare Turnstile detected.")
#             return self._solve_challenge(driver)
#
#         except Exception as e:
#             print("No Cloudflare Turnstile challenge found or timed out.")
#             return True  # Proceed as normal if not present
#
#     def _solve_challenge(self, driver: webdriver.Chrome) -> bool:
#         """Solve Turnstile challenge using 2Captcha."""
#         try:
#             WebDriverWait(driver, 5).until(
#                 lambda d: d.execute_script("return typeof window._cf_chl_opt !== 'undefined';")
#             )
#
#             config = driver.execute_script("return window._cf_chl_opt || {}")
#
#             site_key = config.get("chlApiSitekey")
#             url = driver.current_url
#             mode = config.get("chlApiMode")
#             ray = config.get("cRay")
#             pagedata = config.get("chlApiRcV")
#
#             if not site_key:
#                 print("Site key not found in page config.")
#                 return False
#
#             payload = {
#                 "sitekey": site_key,
#                 "url": url,
#                 "action": mode,
#                 "data": ray,
#                 "pagedata": pagedata,
#             }
#
#             print(f"Sending Turnstile challenge to solver: {payload}")
#             result = self.solver.turnstile(**payload)
#
#             if result and 'code' in result:
#                 token = result['code']
#                 js = f"""
#                     var respInput = document.querySelector('[name="cf-turnstile-response"]');
#                     if (respInput) {{
#                         respInput.value = '{token}';
#                         var form = respInput.closest('form');
#                         if (form) form.submit();
#                     }}
#                 """
#                 driver.execute_script(js)
#                 time.sleep(3)
#                 print("Turnstile challenge solved and form submitted.")
#                 return True
#
#             print("Solver did not return a valid code.")
#             return False
#
#         except Exception as e:
#             print(f"Exception while solving Turnstile: {e}")
#             return False

class OptimizedCloudflareHandler:
    """Optimized handler for Cloudflare Turnstile CAPTCHA."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("CAPCHA_KEY")
        self.solver = TwoCaptcha(self.api_key)
        self.logger = logging.getLogger(__name__)

    def handle_protection(self, driver: webdriver.Chrome, max_wait: int = 10) -> bool:
        """
        Detect and solve Cloudflare Turnstile challenge if present.
        Returns True if passed or no challenge found.
        """
        page = driver.page_source.lower()
        return (
                "verify you are human" in page or
                "cf-turnstile-response" in page or
                "needs to review the security" in page
        )
        # try:
        #     print("🔍 Waiting for page to load...")
        #     WebDriverWait(driver, max_wait).until(
        #         lambda d: d.execute_script("return document.readyState === 'complete'")
        #     )
        #
        #     print("🔍 Checking for Turnstile iframe...")
        #     WebDriverWait(driver, max_wait).until(
        #         EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'challenges.cloudflare.com')]"))
        #     )
        #
        #     print("⚠️ Turnstile challenge iframe found.")
        #     # return self._solve_challenge(driver)
        #     return True
        #
        # except TimeoutException:
        #     print("✅ No Turnstile challenge iframe found (or timeout).")
        #     return False  # Proceed as normal if iframe not found
        # except Exception as e:
        #     print(f"⚠️ Exception in handle_protection: {e}")
        #     return False

    def _solve_challenge(self, driver: webdriver.Chrome) -> bool:
        """Solve Turnstile challenge using 2Captcha (iframe or config-based)."""
        try:
            sitekey = None
            url = driver.current_url

            # 1. Look for iframe with Turnstile
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                src = iframe.get_attribute("src")
                if src and "challenges.cloudflare.com" in src:
                    print(f"✅ Found Turnstile iframe: {src}")
                    driver.switch_to.frame(iframe)
                    try:
                        elem = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-sitekey]"))
                        )
                        sitekey = elem.get_attribute("data-sitekey")
                        print(f"✅ Extracted sitekey from iframe: {sitekey}")
                    finally:
                        driver.switch_to.default_content()
                    break

            # 2. Fallback: try extracting from window config
            if not sitekey:
                try:
                    WebDriverWait(driver, 3).until(
                        lambda d: d.execute_script("return typeof window._cf_chl_opt !== 'undefined';")
                    )
                    config = driver.execute_script("return window._cf_chl_opt || {}")
                    sitekey = config.get("chlApiSitekey")
                except Exception:
                    pass

            if not sitekey:
                print("❌ Could not find Turnstile sitekey.")
                return False

            # Send to 2Captcha
            print(f"✅ Found Turnstile sitekey: {sitekey}")
            result = self.solver.turnstile(sitekey=sitekey, url=url)

            if result and 'code' in result:
                token = result['code']
                print("✅ Received Turnstile token from solver.")

                # Insert token and submit
                driver.execute_script(f"""
                    let input = document.querySelector('[name="cf-turnstile-response"]');
                    if (input) {{
                        input.value = "{token}";
                        let form = input.closest('form');
                        if (form) form.submit();
                    }}
                """)
                time.sleep(3)
                return True

            print("❌ Solver did not return a token.")
            return False

        except Exception as e:
            print(f"⚠️ Exception while solving Turnstile: {e}")
            return False


class ConcurrentAirlineScraper:
    """Main scraper class that handles all airline types concurrently"""

    def __init__(self, max_workers: int = 9, proxy_ip: str = None):
        self.max_workers = max_workers
        self.proxy_ip = proxy_ip
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
            # Create optimized driver with proxy IP and airline name
            driver_manager = OptimizedWebDriverManager(headless=True, proxy_ip=self.proxy_ip)
            driver = driver_manager.create_driver(airline_config.key, airline_config.group)

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
        """Optimized Crane.aero scraping with driver reset on retry"""

        MAX_RETRIES = 4
        retries = 0

        while retries <= MAX_RETRIES:
            try:
                print(f"🔍 Attempt {retries + 1}: {airline_config.name}")

                # For retries after the first, create a fresh driver
                if retries > 0:
                    print("♻️ Restarting browser session...")
                    driver.quit()
                    driver = OptimizedWebDriverManager().create_driver(airline_config.key, airline_config.group)

                driver.get(airline_config.url)

                if self.cloudflare_handler.handle_protection(driver):
                    print("⚠️ Cloudflare protection detected.")
                    retries += 1
                    time.sleep(2)
                    continue

                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "trip-type-wrapper"))
                )

                self._fill_crane_form_optimized(driver, search_config)
                self._submit_crane_search(driver)
                return self._extract_crane_results_optimized(driver, search_config.trip_type, airline_config.key)

            except Exception as e:
                self.logger.error(f"❌ Scrape attempt {retries + 1} failed: {e}")
                retries += 1

        self.logger.error(f"❌ Max retries exceeded for {airline_config.name}")
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
            self._fill_videcom_form_optimized(driver, search_config, airline_config.key)

            # Submit and wait for results
            self._submit_videcom_search(driver)

            # Extract results
            return self._extract_videcom_results_optimized(driver, search_config.trip_type, airline_config.key)

        except Exception as e:
            self.logger.error(f"Videcom scraping error for {airline_config.name}: {e}")
            return None

    def _scrape_overland_airline(self, driver: webdriver.Chrome, airline_config: AirlineConfig,
                                 search_config: FlightSearchConfig) -> Optional[Dict]:
        """Scrape Overland Airways flights"""
        try:
            driver.get(airline_config.url)

            # Wait for the page to be fully loaded
            WebDriverWait(driver, 10).until(
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

    def _fill_videcom_form_optimized(self, driver: webdriver.Chrome, config: FlightSearchConfig, airline_name: str):
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
            time.sleep(2)

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
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "availability-flight-table-0"))
            )
            time.sleep(3)  # Reduced wait time

        except Exception as e:
            self.logger.error(f"Error submitting Crane search: {e}")

    def _submit_videcom_search(self, driver: webdriver.Chrome):
        """Submit Videcom search form and handle reCAPTCHA if present"""
        try:
            # Click the submit button
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "submitButton"))
            )
            submit_button.click()

            # Check if reCAPTCHA is present
            try:
                # Wait for either reCAPTCHA or results with a short timeout
                WebDriverWait(driver, 5).until(
                    lambda d: d.find_elements(By.CLASS_NAME, "g-recaptcha") or d.find_elements(By.ID, "calView_0")
                )
                
                # If reCAPTCHA is present, handle it
                if driver.find_elements(By.CLASS_NAME, "g-recaptcha"):
                    recaptcha_element = driver.find_element(By.CLASS_NAME, "g-recaptcha")
                    sitekey = recaptcha_element.get_attribute("data-sitekey")
                    self.logger.info(f"Found reCAPTCHA with sitekey: {sitekey}")

                    # Get current URL for captcha solving
                    current_url = driver.current_url

                    # Solve the captcha using 2Captcha
                    solver = TwoCaptcha(os.getenv("CAPCHA_KEY"))
                    try:
                        result = solver.recaptcha(
                            sitekey=sitekey,
                            url=current_url
                        )
                        
                        if result and 'code' in result:
                            # Insert the solved captcha token
                            token = result['code']
                            self.logger.info("Successfully solved reCAPTCHA")
                            
                            # Execute JavaScript to set the token
                            driver.execute_script(f"""
                                document.querySelector('[id="g-recaptcha-response"]').innerText = '{token}';
                            """)
                            
                            # Trigger the callback function
                            driver.execute_script("recaptchaCallback(arguments[0]);", token)
                            
                            # Wait for results after captcha submission
                            WebDriverWait(driver, 15).until(
                                EC.presence_of_element_located((By.ID, "calView_0"))
                            )
                            time.sleep(3)
                        else:
                            raise Exception("Failed to get captcha solution")
                            
                    except Exception as e:
                        self.logger.error(f"Error solving reCAPTCHA: {str(e)}")
                        raise
                else:
                    # No reCAPTCHA found, just wait for results
                    self.logger.info("No reCAPTCHA found, proceeding with search")
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.ID, "calView_0"))
                    )
                    time.sleep(3)

            except Exception as e:
                self.logger.error(f"Error handling search submission: {str(e)}")
                raise

        except Exception as e:
            self.logger.error(f"Error submitting Videcom search: {e}")
            raise

    def _extract_crane_results_optimized(self, driver: webdriver.Chrome, trip_type: TripType,
                                         airline_name) -> Dict:
        """Optimized Crane results extraction"""
        try:
            results = {}

            # Extract departure flights
            departure_flights = self._extract_flights_table(driver, "availability-flight-table-0",
                                                            "crane", airline_name)
            if departure_flights:
                results['departure'] = departure_flights

            # Extract return flights for round trips
            if trip_type == TripType.ROUND_TRIP:
                return_flights = self._extract_flights_table(driver, "availability-flight-table-1",
                                                             "crane", airline_name)
                if return_flights:
                    results['return'] = return_flights

            return results if results else None

        except Exception as e:
            self.logger.error(f"Error extracting Crane results: {e}")
            return None

    def _extract_videcom_results_optimized(self, driver: webdriver.Chrome, trip_type: TripType, airline_name) -> Dict:
        """Optimized Videcom results extraction"""
        try:
            results = {}

            # Extract departure flights
            departure_flights = self._extract_flights_table(driver, "calView_0", "videcom", airline_name)
            if departure_flights:
                results['departure'] = departure_flights

            # Extract return flights for round trips
            if trip_type == TripType.ROUND_TRIP:
                return_flights = self._extract_flights_table(driver, "calView_1", "videcom", airline_name)
                if return_flights:
                    results['return'] = return_flights

            return results if results else None

        except Exception as e:
            self.logger.error(f"Error extracting Videcom results: {e}")
            return None

    def _extract_flights_table(self, driver: webdriver.Chrome, table_id: str, airline_type: str, airline_name: str) -> \
            List[Dict]:
        """Extract flights from table using BeautifulSoup and parallel processing"""

        try:
            # Wait for table to be present
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, table_id))
            )

            # Get the table HTML
            table_html = driver.find_element(By.ID, table_id).get_attribute('outerHTML')
            soup = BeautifulSoup(table_html, 'html.parser')

            # Find all flight elements based on airline type
            if airline_type == "crane":
                flight_elements = soup.select(".js-journey")
            else:  # videcom
                flight_elements = soup.select(".flt-panel")

            def process_flight(flight_element):
                try:
                    if airline_type == "crane":
                        return self._extract_crane_flight_data(flight_element, airline_name)
                    else:
                        return self._extract_videcom_flight_data(flight_element)
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

    def _extract_crane_flight_data(self, flight_element, airline_name) -> Optional[Dict]:
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

    def _extract_videcom_flight_data(self, flight_element) -> Optional[Dict]:
        """Extract Videcom flight data using BeautifulSoup"""
        try:
            flight_data = {
                "flight_number": self._safe_extract_text_bs(flight_element, ".flightnumber"),
                "departure": {
                    "time": self._safe_extract_text_bs(flight_element, ".cal-Depart-time .time"),
                    "city": self._safe_extract_text_bs(flight_element, ".cal-Depart-time .city"),
                    "date": self._safe_extract_text_bs(flight_element, ".cal-Depart-time .flightDate")
                },
                "arrival": {
                    "time": self._safe_extract_text_bs(flight_element, ".cal-Arrive-time .time"),
                    "city": self._safe_extract_text_bs(flight_element, ".cal-Arrive-time .city"),
                    "date": self._safe_extract_text_bs(flight_element, ".cal-Arrive-time .flightDate")
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

    def _fill_overland_form(self, driver: webdriver.Chrome, config: FlightSearchConfig):
        """Fill Overland Airways search form"""
        try:
            # Set trip type
            trip_type_select = WebDriverWait(driver, 20).until(
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
            departure_input = WebDriverWait(driver, 20).until(
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
            arrival_input = WebDriverWait(driver, 20).until(
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

            WebDriverWait(driver, 20).until(
                EC.invisibility_of_element_located((By.ID, "overlay1"))
            )

            # Set passengers
            passengers_input = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "flightForm_passengers"))
            )
            passengers_input.click()
            wait(1, 2)

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

    def _extract_overland_flights_table(self, driver, table_id: str, label: str) -> List[Dict]:
        """Extract flights from Overland table with Selenium, BeautifulSoup, and concurrency"""
        try:
            table = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, table_id))
            )

            flights = table.find_elements(By.CLASS_NAME, "flightItemNew")
            flight_list = []

            def process_flight(flight):
                try:
                    flight_data = {
                        "flight_number": None,
                        "departure": {"time": None, "city": None, "date": None},
                        "arrival": {"time": None, "city": None, "date": None},
                        "price": None,
                        "status": None,
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
                        depart_info = depart_block.select_one("span").text.strip()
                        depart_date, depart_city = depart_info.split("|")
                        flight_data["departure"]["date"] = depart_date.strip()
                        flight_data["departure"]["city"] = depart_city.strip()
                    except:
                        pass

                    # Arrival
                    try:
                        arrive_block = soup.select(".flightItem_titleLeft .flightItem_titleTime")[1]
                        flight_data["arrival"]["time"] = arrive_block.select_one("strong").text.strip()
                        arrive_info = arrive_block.select_one("span").text.strip()
                        arrive_date, arrive_city = arrive_info.split("|")
                        flight_data["arrival"]["date"] = arrive_date.strip()
                        flight_data["arrival"]["city"] = arrive_city.strip()
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
                            wait(2, 3)

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
            scraper = ConcurrentAirlineScraper(max_workers=9, proxy_ip=proxy_ip)
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
            scraper = ConcurrentAirlineScraper(max_workers=9, proxy_ip=proxy_ip)
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
