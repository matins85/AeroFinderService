from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AirportViewSet, FlightSearchViewSet

router = DefaultRouter()
router.register(r'airports', AirportViewSet, basename='airport')
router.register(r'search', FlightSearchViewSet, basename='flight-search')

urlpatterns = [
    path('', include(router.urls)),
]

