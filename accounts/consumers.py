import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .views import ConcurrentAirlineScraper, FlightSearchConfig, TripType, AIRLINES_CONFIG
import logging

logger = logging.getLogger(__name__)


class FlightSearchConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f'search_{self.session_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"WebSocket connected for session {self.session_id}")

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected for session {self.session_id}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            search_config = await self._create_search_config(data)

            if not search_config:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Invalid search parameters'
                }))
                return

            # Start the search process
            airlines = data.get('airlines', None)
            if isinstance(airlines, str):
                airlines = [a.strip() for a in airlines.split(',') if a.strip()]
            await self._start_search(search_config, airlines=airlines)

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON data'
            }))
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def _start_search(self, search_config, airlines=None):
        """Start the flight search process and stream results"""
        try:
            # Create scraper instance with proxy IP
            proxy_ip = search_config.get('proxyIP')
            scraper = ConcurrentAirlineScraper(proxy_ip=proxy_ip)

            # Get airline filter if specified
            airline = search_config.get('airline')

            # Start the search process
            await self._stream_search_results(scraper, search_config, airline, airlines)

        except Exception as e:
            logger.error(f"Error in search process: {str(e)}")
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'error',
                    'message': str(e)
                }
            )

    async def _stream_search_results(self, scraper, search_config, airline=None, airlines=None):
        """Stream search results as they become available"""
        try:
            # Convert search_config dict to FlightSearchConfig object
            config = FlightSearchConfig(
                departure_city=search_config['departure_city'],
                arrival_city=search_config['arrival_city'],
                departure_date=search_config['departure_date'],
                return_date=search_config.get('return_date', '10 Jun 2025'),
                adults=int(search_config.get('adults', 1)),
                children=int(search_config.get('children', 0)),
                infants=int(search_config.get('infants', 0)),
                trip_type=TripType(search_config.get('trip_type', 'round-trip'))
            )

            # Use the generator to get results as they complete
            loop = asyncio.get_event_loop()

            # Run the concurrent search in a thread to avoid blocking
            def run_search():
                return list(scraper.search_all_airlines(config, airline, airlines))

            # Get results as they stream in
            try:
                # This will run the generator in a separate thread
                results_generator = await loop.run_in_executor(None, run_search)

                # Process each result as it arrives
                for airline_key, result in results_generator:
                    # Log the completion status
                    if result.get('error'):
                        logger.warning(f"❌ {airline_key} search failed: {result['error']}")
                    else:
                        flight_count = len(result.get('flights', [])) if isinstance(result, dict) else 0
                        logger.info(f"✅ {airline_key} search completed - {flight_count} flights found")

                    # Send result immediately to WebSocket client
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "search_result",
                            "result": {
                                "type": "search_result",
                                "airline": airline_key,
                                "data": result,
                                "timestamp": asyncio.get_event_loop().time()
                            }
                        }
                    )

            except Exception as e:
                logger.error(f"Error in concurrent search: {str(e)}")
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'error',
                        'message': str(e)
                    }
                )
                return

            # Send completion message after all results are processed
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'search_complete',
                    'message': 'All airline searches completed'
                }
            )

            # Send completion message after all results are processed
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'search_complete',
                    'message': 'All airline searches completed'
                }
            )

            # Filter airlines if specific airline is requested
            # airlines_to_search = [config for config in AIRLINES_CONFIG if not airline or config.key == airline.lower()]

            # if not airlines_to_search:
            #     logger.warning(f"No airlines found matching '{airline}'")
            #     await self.channel_layer.group_send(
            #         self.room_group_name,
            #         {
            #             'type': 'error',
            #             'message': f"No airlines found matching '{airline}'"
            #         }
            #     )
            #     return

            # # Create tasks for each airline search
            # loop = asyncio.get_event_loop()
            # tasks = []

            # for airline_config in airlines_to_search:
            #     # Create a task for each airline search
            #     task = loop.run_in_executor(
            #         None,
            #         lambda ac=airline_config: scraper._search_single_airline(ac, config)
            #     )
            #     tasks.append((airline_config.key, task))

            # # Process results as they complete
            # for airline_key, task in tasks:
            #     try:
            #         result = await task
            #         # Send result immediately as it arrives
            #         await self.channel_layer.group_send(
            #             self.room_group_name,
            #             {
            #                 "type": "search_result",
            #                 "result": {
            #                     "type": "search_result",
            #                     "airline": airline_key,
            #                     "data": result
            #                 }
            #             }
            #         )
            #     except Exception as e:
            #         logger.error(f"Error searching {airline_key}: {str(e)}")
            #         await self.channel_layer.group_send(
            #             self.room_group_name,
            #             {
            #                 "type": "search_result",
            #                 "result": {
            #                     "type": "search_result",
            #                     "airline": airline_key,
            #                     "data": {
            #                         "success": False,
            #                         "error": str(e)
            #                     }
            #                 }
            #             }
            #         )

            # # Send completion message after all results are processed
            # await self.channel_layer.group_send(
            #     self.room_group_name,
            #     {
            #         'type': 'search_complete',
            #         'message': 'Search completed'
            #     }
            # )

        except Exception as e:
            logger.error(f"Error streaming results: {str(e)}")
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'error',
                    'message': str(e)
                }
            )

    @database_sync_to_async
    def _create_search_config(self, data):
        """Create and validate search configuration from WebSocket data"""
        try:
            # Required parameters
            departure_city = data.get('departure_city')
            arrival_city = data.get('arrival_city')
            departure_date = data.get('departure_date')

            if not all([departure_city, arrival_city, departure_date]):
                return None

            # Optional parameters with defaults
            return_date = data.get('return_date', '10 Jun 2025')
            trip_type = data.get('trip_type', 'round-trip')
            adults = int(data.get('adults', 1))
            children = int(data.get('children', 0))
            infants = int(data.get('infants', 0))
            airline = data.get('airline')
            proxy_ip = data.get('proxyIP')  # Get the proxy IP from the data
            airlines = data.get('airlines', None)

            # Validate passenger counts
            if adults < 1 or adults > 9:
                raise ValueError("Adults must be between 1 and 9")
            if children < 0 or children > 8:
                raise ValueError("Children must be between 0 and 8")
            if infants < 0 or infants > adults:
                raise ValueError("Infants cannot exceed number of adults")

            return {
                'departure_city': departure_city,
                'arrival_city': arrival_city,
                'departure_date': departure_date,
                'return_date': return_date,
                'trip_type': trip_type,
                'adults': adults,
                'children': children,
                'infants': infants,
                'airline': airline,
                'airlines': airlines,
                'proxyIP': proxy_ip  # Include the proxy IP in the returned config
            }

        except (ValueError, TypeError) as e:
            logger.warning(f"Config creation error: {str(e)}")
            raise ValueError(f"Invalid parameter: {str(e)}")

    async def search_result(self, event):
        """Send search result to WebSocket"""
        await self.send(text_data=json.dumps(event['result']))

    async def search_complete(self, event):
        """Send search completion message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'complete',
            'message': event['message']
        }))

    async def error(self, event):
        """Send error message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': event['message']
        }))
