import logging
import time
import shutil
import subprocess
import re
import os
import tempfile
from typing import Optional
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from twocaptcha import TwoCaptcha
import undetected_chromedriver as uc


class OptimizedWebDriverManager:
    """Optimized WebDriver manager with better resource management"""

    def __init__(self, headless: bool = False, proxy_ip: str = None):
        self.headless = headless
        self.proxy_ip = proxy_ip
        self.logger = logging.getLogger(__name__)

    def create_driver(self, airline_name: str = None, airline_type: str = None) -> webdriver.Chrome:
        """Create optimized Chrome WebDriver with optional proxy per airline."""
        user_agent = UserAgent()
        options = uc.ChromeOptions()

        user_data_dir = tempfile.mkdtemp(prefix='chrome_user_data_')
        self.logger.info(f"Created unique Chrome user data directory: {user_data_dir}")

        chrome_options = [
            f"--user-agent={user_agent.random}",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--disable-gpu-sandbox",
            "--window-size=1366,768",
            "--disable-infobars",
            "--lang=en-NG",
            "--ignore-certificate-errors",
            "--enable-unsafe-swiftshader",
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
            "--proxy-server='direct://'",
            "--proxy-bypass-list=*"
        ]

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

        # Path to chromedriver
        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
        try:
            driver = uc.Chrome(
                driver_executable_path=chromedriver_path,
                options=options,
                headless=self.headless
            )
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

        # Option 1: Try webdriver-manager FIRST (automatically matches Chrome version)
        # This should be prioritized to avoid version mismatches
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()
            print(driver_path, 'driver_path')
            if os.access(driver_path, os.X_OK):
                self.logger.info(f"Using webdriver-manager ChromeDriver (auto-matched version): {driver_path}")
                return Service(driver_path)
            else:
                self.logger.warning(f"ChromeDriver at {driver_path} is not executable")
        except Exception as e:
            self.logger.warning(f"webdriver-manager failed: {e}")

        # Option 2: Try system ChromeDriver (installed via brew or apt)
        chromedriver_path = shutil.which('chromedriver')
        if chromedriver_path:
            self.logger.info(f"Using system ChromeDriver: {chromedriver_path}")
            return Service(chromedriver_path)

        # Option 3: Try common installation paths
        common_paths = [
            '/usr/local/bin/chromedriver',
            '/opt/homebrew/bin/chromedriver',  # Apple Silicon Macs
            '/usr/bin/chromedriver',
        ]
        for path in common_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                self.logger.info(f"Using ChromeDriver at: {path}")
                return Service(path)

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


class OptimizedCloudflareHandler:
    """Optimized handler for Cloudflare Turnstile CAPTCHA and challenges."""

    def __init__(self, api_key: str = None):
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key or os.getenv("CAPCHA_KEY")
        if self.api_key:
            self.solver = TwoCaptcha(self.api_key)
        else:
            self.solver = None
            self.logger.warning("⚠️ CAPCHA_KEY not set. Cloudflare solving will not work.")

    def handle_protection(self, driver: webdriver.Chrome, max_wait: int = 10) -> bool:
        """
        Detect and solve Cloudflare challenge if present.
        Returns True if passed or no challenge found, False if challenge failed.
        """
        try:
            # Wait for page to load
            WebDriverWait(driver, max_wait).until(
                lambda d: d.execute_script("return document.readyState === 'complete'")
            )
            time.sleep(3)  # Give Cloudflare time to show challenge if present

            # Check for Cloudflare protection indicators
            page_source = driver.page_source.lower()
            page_url = driver.current_url.lower()
            page_title = driver.title.lower()
            
            # Check for Cloudflare challenge page
            cloudflare_indicators = [
                "challenges.cloudflare.com" in page_source,
                "challenges.cloudflare.com" in page_url,
                "cf-browser-verification" in page_source,
                "cf-challenge" in page_source,
                "just a moment" in page_title or "just a moment" in page_source,
                "checking your browser" in page_source,
                "verifying you are human" in page_source,
                "cf-turnstile" in page_source,
                "turnstile" in page_source,
            ]
            
            if any(cloudflare_indicators):
                self.logger.warning("⚠️ Cloudflare protection detected")
                
                # Check if Turnstile widget is present (needs solving)
                # Priority: Check for actual Turnstile elements first
                has_turnstile = (
                    driver.find_elements(By.CSS_SELECTOR, "iframe[src*='turnstile']") or
                    driver.find_elements(By.CSS_SELECTOR, "iframe[src*='challenges.cloudflare.com/cdn-cgi/challenge-platform']") or
                    driver.find_elements(By.CSS_SELECTOR, "[name='cf-turnstile-response']") or
                    driver.find_elements(By.CSS_SELECTOR, "[id*='cf-chl-widget'][id*='response']") or
                    "cf-turnstile" in page_source or
                    "turnstile" in page_source
                )
                
                if has_turnstile:
                    self.logger.info("🔍 Detected Turnstile challenge, attempting to solve...")
                    if not self.solver:
                        self.logger.error("❌ 2Captcha API key not set. Cannot solve Turnstile.")
                        return False
                    return self._solve_challenge(driver)
                
                # Check for 5-second challenge (auto-resolves, no explicit Turnstile widget)
                # This is when we see "Just a moment..." or "Verifying you are human" but no Turnstile iframe
                is_5_second_challenge = (
                    ("just a moment" in page_title or "just a moment" in page_source) or
                    ("verifying you are human" in page_source and not has_turnstile) or
                    ("checking your browser" in page_source and not has_turnstile)
                )
                
                if is_5_second_challenge:
                    self.logger.info("🔄 Detected 5-second challenge, waiting for auto-resolution...")
                    return self._wait_for_5_second_challenge(driver)
            
            # No Cloudflare protection detected
            self.logger.info("✅ No Cloudflare protection detected")
            return True

        except TimeoutException:
            self.logger.info("✅ No Cloudflare challenge detected (timeout)")
            return True
        except Exception as e:
            self.logger.error(f"⚠️ Exception in handle_protection: {e}")
            return False

    def _wait_for_5_second_challenge(self, driver: webdriver.Chrome, max_wait: int = 20) -> bool:
        """Wait for Cloudflare 5-second challenge to auto-resolve"""
        try:
            self.logger.info("⏳ Waiting for Cloudflare 5-second challenge to auto-resolve...")
            start_time = time.time()
            last_url = driver.current_url
            
            while time.time() - start_time < max_wait:
                current_url = driver.current_url.lower()
                page_source = driver.page_source.lower()
                page_title = driver.title.lower()
                
                # Check if challenge is resolved by multiple indicators
                challenge_indicators = [
                    "just a moment" in page_title,
                    "just a moment" in page_source,
                    "checking your browser" in page_source,
                    "verifying you are human" in page_source,
                    "challenges.cloudflare.com" in current_url,
                ]
                
                # If none of the challenge indicators are present, challenge is likely resolved
                if not any(challenge_indicators):
                    # Additional check: URL changed or we're on the actual site
                    if current_url != last_url or "challenges.cloudflare.com" not in current_url:
                        self.logger.info("✅ 5-second challenge resolved (indicators cleared)")
                        time.sleep(2)  # Wait for page to fully load
                        return True
                
                # Check if URL changed (redirected away from challenge page)
                if current_url != last_url and "challenges.cloudflare.com" not in current_url:
                    self.logger.info("✅ 5-second challenge resolved (URL redirected)")
                    time.sleep(2)  # Wait for page to fully load
                    return True
                
                last_url = current_url
                time.sleep(1)
            
            # Final check
            current_url = driver.current_url.lower()
            page_source = driver.page_source.lower()
            page_title = driver.title.lower()
            
            if ("challenges.cloudflare.com" not in current_url and
                "just a moment" not in page_title and
                "verifying you are human" not in page_source):
                self.logger.info("✅ 5-second challenge appears resolved (final check)")
                return True
            
            self.logger.warning("⚠️ 5-second challenge did not resolve in time")
            return False
        except Exception as e:
            self.logger.error(f"Error waiting for 5-second challenge: {e}")
            return False

    def _solve_challenge(self, driver: webdriver.Chrome) -> bool:
        """Solve Cloudflare Turnstile challenge using 2Captcha"""
        try:
            sitekey = None
            url = driver.current_url
            # Remove Cloudflare challenge parameters from URL for solving
            clean_url = url.split('?')[0] if '?' in url else url
            # Also remove __cf_chl_* parameters if present
            if '__cf_chl' in clean_url:
                clean_url = clean_url.split('&__cf_chl')[0].split('?__cf_chl')[0]

            # Wait for Turnstile widget to load
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='turnstile'], iframe[src*='challenges.cloudflare.com']"))
                )
            except:
                pass

            # Method 1: Extract sitekey from Turnstile iframe URL or attributes
            try:
                iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='turnstile'], iframe[src*='challenges.cloudflare.com']")
                for iframe in iframes:
                    src = iframe.get_attribute("src")
                    if src and "turnstile" in src:
                        self.logger.info(f"✅ Found Turnstile iframe: {src[:100]}...")
                        
                        # Try to get sitekey from iframe's data attributes
                        try:
                            sitekey = iframe.get_attribute("data-sitekey")
                            if not sitekey:
                                sitekey = iframe.get_attribute("sitekey")
                            if sitekey:
                                self.logger.info(f"✅ Extracted sitekey from iframe attribute: {sitekey[:20]}...")
                                break
                        except:
                            pass
                        
                        # Try extracting from iframe content
                        try:
                            driver.switch_to.frame(iframe)
                            iframe_content = driver.page_source
                            match = re.search(r'sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']', iframe_content, re.IGNORECASE)
                            if match:
                                sitekey = match.group(1)
                                self.logger.info(f"✅ Extracted sitekey from iframe content: {sitekey[:20]}...")
                            driver.switch_to.default_content()
                            if sitekey:
                                break
                        except:
                            driver.switch_to.default_content()
            except Exception as e:
                self.logger.warning(f"Error extracting from iframe: {e}")

            # Method 2: Extract sitekey from page source (regex patterns)
            if not sitekey:
                page_source = driver.page_source
                sitekey_patterns = [
                    r'data-sitekey=["\']([^"\']+)["\']',
                    r'sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                    r'cf-turnstile["\'][^"\']*sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                    r'turnstile["\'][^"\']*sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                ]
                
                for pattern in sitekey_patterns:
                    match = re.search(pattern, page_source, re.IGNORECASE)
                    if match:
                        sitekey = match.group(1)
                        # Validate sitekey format (usually alphanumeric, ~40 chars)
                        if len(sitekey) > 20:
                            self.logger.info(f"✅ Extracted sitekey from page source: {sitekey[:20]}...")
                            break

            # Method 3: Try extracting from window config (_cf_chl_opt)
            if not sitekey:
                try:
                    WebDriverWait(driver, 3).until(
                        lambda d: d.execute_script("return typeof window._cf_chl_opt !== 'undefined';")
                    )
                    config = driver.execute_script("return window._cf_chl_opt || {}")
                    # Try multiple possible keys
                    sitekey = (config.get("chlApiSitekey") or 
                              config.get("sitekey") or 
                              config.get("cApiSitekey") or
                              config.get("apiSitekey"))
                    if sitekey:
                        self.logger.info(f"✅ Extracted sitekey from window config: {sitekey[:20]}...")
                except Exception:
                    pass

            # Method 4: Try to get sitekey from Turnstile API script URL
            if not sitekey:
                try:
                    scripts = driver.find_elements(By.TAG_NAME, "script")
                    for script in scripts:
                        src = script.get_attribute("src")
                        if src and "turnstile" in src and ("api.js" in src or "challenge-platform" in src):
                            # Extract sitekey from script URL parameters
                            match = re.search(r'sitekey=([^&"\']+)', src)
                            if match:
                                sitekey = match.group(1)
                                self.logger.info(f"✅ Extracted sitekey from script URL: {sitekey[:20]}...")
                                break
                except Exception:
                    pass

            # Method 5: Try extracting from iframe URL directly (some Turnstile implementations)
            if not sitekey:
                try:
                    iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='turnstile']")
                    for iframe in iframes:
                        src = iframe.get_attribute("src")
                        # Some Turnstile iframes have sitekey in the URL path
                        match = re.search(r'/0x([A-Za-z0-9+/=]{40,})', src)
                        if match:
                            # This might be encoded sitekey, but let's try other methods first
                            pass
                except Exception:
                    pass

            if not sitekey:
                self.logger.error("❌ Could not find Turnstile sitekey")
                return False

            # Solve using 2Captcha
            self.logger.info(f"🔐 Solving Turnstile challenge with sitekey: {sitekey[:20]}...")
            try:
                result = self.solver.turnstile(sitekey=sitekey, url=clean_url)
            except Exception as e:
                self.logger.error(f"❌ 2Captcha API error: {e}")
                return False

            if result and 'code' in result:
                token = result['code']
                self.logger.info("✅ Received Turnstile token from solver")

                # Inject token using multiple methods
                injection_result = driver.execute_script(f"""
                    (function() {{
                        let token = '{token}';
                        let injected = false;
                        let methods = [];
                        
                        // Method 1: Find by name attribute (most reliable)
                        let inputs = document.querySelectorAll('[name="cf-turnstile-response"]');
                        if (inputs.length > 0) {{
                            for (let input of inputs) {{
                                input.value = token;
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                            }}
                            injected = true;
                            methods.push('name-attribute');
                        }}
                        
                        // Method 2: Find by ID pattern (cf-chl-widget-*_response)
                        if (!injected) {{
                            inputs = document.querySelectorAll('[id*="cf-chl-widget"][id*="response"]');
                            if (inputs.length > 0) {{
                                for (let input of inputs) {{
                                    input.value = token;
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                }}
                                injected = true;
                                methods.push('id-pattern');
                            }}
                        }}
                        
                        // Method 3: Find any hidden input with turnstile in name/id
                        if (!injected) {{
                            inputs = document.querySelectorAll('input[type="hidden"]');
                            for (let input of inputs) {{
                                if ((input.name && input.name.includes('turnstile')) || 
                                    (input.id && input.id.includes('turnstile'))) {{
                                    input.value = token;
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    injected = true;
                                    methods.push('hidden-input');
                                    break;
                                }}
                            }}
                        }}
                        
                        // Method 4: Try to set via window.turnstile if available
                        if (window.turnstile) {{
                            try {{
                                // Try to find the widget and set token
                                let widgets = document.querySelectorAll('[data-sitekey]');
                                if (widgets.length > 0) {{
                                    // Token is already set via input, but trigger callback
                                    if (window.turnstile.reset) {{
                                        window.turnstile.reset();
                                    }}
                                    methods.push('turnstile-reset');
                                }}
                            }} catch(e) {{
                                console.log('Turnstile API error:', e);
                            }}
                        }}
                        
                        // Method 5: Trigger callback if exists
                        if (typeof turnstileCallback !== 'undefined') {{
                            try {{
                                turnstileCallback(token);
                                methods.push('callback');
                            }} catch(e) {{
                                console.log('turnstileCallback error:', e);
                            }}
                        }}
                        
                        // Try to submit form if present
                        try {{
                            let forms = document.querySelectorAll('form');
                            if (forms.length > 0 && injected) {{
                                // Don't actually submit, just trigger events
                                forms[0].dispatchEvent(new Event('submit', {{ bubbles: true, cancelable: true }}));
                            }}
                        }} catch(e) {{
                            console.log('Form submit error:', e);
                        }}
                        
                        return {{ injected: injected, methods: methods }};
                    }})();
                """)

                if injection_result and injection_result.get('injected'):
                    self.logger.info(f"✅ Token injected successfully using methods: {', '.join(injection_result.get('methods', []))}")
                    # Wait for challenge to complete
                    time.sleep(3)
                    
                    # Check if challenge is resolved by monitoring URL and page changes
                    max_wait = 15
                    start_time = time.time()
                    initial_url = driver.current_url
                    
                    while time.time() - start_time < max_wait:
                        current_url = driver.current_url.lower()
                        page_title = driver.title.lower()
                        page_source = driver.page_source.lower()
                        
                        # Check if we're no longer on challenge page
                        challenge_indicators = [
                            "challenges.cloudflare.com" in current_url,
                            "just a moment" in page_title,
                            "verifying you are human" in page_source,
                            "checking your browser" in page_source,
                        ]
                        
                        if not any(challenge_indicators):
                            self.logger.info("✅ Cloudflare challenge resolved (indicators cleared)")
                            time.sleep(2)  # Wait for page to fully load
                            return True
                        
                        # Check if URL changed (redirected away from challenge)
                        if current_url != initial_url.lower() and "challenges.cloudflare.com" not in current_url:
                            self.logger.info("✅ Cloudflare challenge resolved (URL redirected)")
                            time.sleep(2)  # Wait for page to fully load
                            return True
                        
                        time.sleep(1)
                    
                    # Final check
                    final_url = driver.current_url.lower()
                    final_title = driver.title.lower()
                    if ("challenges.cloudflare.com" not in final_url and
                        "just a moment" not in final_title):
                        self.logger.info("✅ Challenge appears resolved (final check)")
                        return True
                    else:
                        self.logger.warning("⚠️ Challenge may not be fully resolved, but proceeding...")
                        return True  # Proceed anyway to avoid blocking
                else:
                    self.logger.error("❌ Failed to inject token - input field not found")
                    return False
            else:
                self.logger.error("❌ Solver did not return a valid token")
                return False

        except Exception as e:
            self.logger.error(f"⚠️ Exception while solving Turnstile: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

