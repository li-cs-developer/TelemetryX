from django.urls import re_path
from .consumers import FleetLiveConsumer

websocket_urlpatterns = [
    re_path(r"^ws/fleet/live/$", FleetLiveConsumer.as_asgi()),
]