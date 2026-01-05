from django.urls import path
from .views import SearchAirLineView

urlpatterns = [
    path('search/', SearchAirLineView.as_view(), name='search-airlines'),
]

