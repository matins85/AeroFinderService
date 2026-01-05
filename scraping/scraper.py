import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional

from selenium import webdriver

from .airline_config import (
    AIRLINES_CONFIG,
    AirlineConfig,
    AirlineGroup,
    FlightSearchConfig,
)
from .scrapers import (
    CraneScraper,
    VidecomScraper,
    OverlandScraper,
    ValueJetScraper,
    GreenAfricaScraper,
)
from .webdriver_manager import OptimizedWebDriverManager, OptimizedCloudflareHandler


class ConcurrentAirlineScraper:
    """Main scraper class that handles all airline types concurrently"""

    def __init__(self, max_workers: int = 11, proxy_ip: str = None):
        self.max_workers = max_workers
        self.proxy_ip = proxy_ip
        self.logger = logging.getLogger(__name__)
        self.cloudflare_handler = OptimizedCloudflareHandler()

    def search_all_airlines(self, search_config: FlightSearchConfig, airline: Optional[str] = None, airlines: Optional[list] = None) -> Dict:
        """
        Search flights across all airlines concurrently
        Args:
            search_config: Flight search configuration
            airline: Optional airline name to filter results (e.g., "airpeace", "arikair", etc.)
            airlines: Optional list of airline keys to filter results (e.g., ["airpeace", "arikair"])
        Returns:
            Dictionary containing flight results from all airlines
        """
        results = {}
        self.logger.info("Starting concurrent airline search...")

        # Determine which airlines to search
        if airlines and isinstance(airlines, list) and len(airlines) > 0:
            airlines_to_search = [config for config in AIRLINES_CONFIG if config.key in [a.lower() for a in airlines]]
        elif airline:
            airlines_to_search = [config for config in AIRLINES_CONFIG if config.key == airline.lower()]
        else:
            airlines_to_search = AIRLINES_CONFIG

        if not airlines_to_search:
            self.logger.warning(f"No airlines found matching '{airline or airlines}'")
            return {"error": f"No airlines found matching '{airline or airlines}'"}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
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
                except Exception as e:
                    self.logger.error(f"❌ Error searching {airline_config.name}: {str(e)}")
                    error_result = {
                        "airline": airline_config.name,
                        "success": False,
                        "data": None,
                        "error": str(e),
                        "search_time": None
                    }
                    results[airline_config.key] = error_result

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
            driver_manager = OptimizedWebDriverManager(headless=False, proxy_ip=self.proxy_ip)
            driver = driver_manager.create_driver(airline_config.key, airline_config.group)

            # Choose scraping strategy based on airline group
            if airline_config.group == AirlineGroup.CRANE_AERO:
                scraper = CraneScraper(logger=self.logger, cloudflare_handler=self.cloudflare_handler, webdriver_manager=driver_manager)
                flight_data = scraper.scrape(driver, airline_config, search_config)
            elif airline_config.group == AirlineGroup.VIDECOM:
                scraper = VidecomScraper(logger=self.logger)
                flight_data = scraper.scrape(driver, airline_config, search_config)
            elif airline_config.group == AirlineGroup.OVERLAND:
                scraper = OverlandScraper(logger=self.logger)
                flight_data = scraper.scrape(driver, airline_config, search_config)
            elif airline_config.group == AirlineGroup.VALUEJET:
                scraper = ValueJetScraper(logger=self.logger)
                flight_data = scraper.scrape(driver, airline_config, search_config)
            elif airline_config.group == AirlineGroup.GREENAFRICA:
                scraper = GreenAfricaScraper(logger=self.logger)
                flight_data = scraper.scrape(driver, airline_config, search_config)
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

