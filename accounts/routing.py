from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/search/(?P<session_id>\w+)/$', consumers.FlightSearchConsumer.as_asgi()),
] 