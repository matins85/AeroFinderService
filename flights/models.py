from django.db import models
from django.conf import settings
import random
import string


class Airport(models.Model):
    """Airport information"""
    airport_code = models.CharField(max_length=10, unique=True)
    description = models.CharField(max_length=200)
    city_country = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    priority = models.IntegerField(default=0)
    
    def __str__(self):
        return f"{self.airport_code} - {self.description}"
    
    class Meta:
        ordering = ['-priority', 'airport_code']


class FlightSearch(models.Model):
    """Flight search record"""
    TRIP_TYPE_CHOICES = [
        ('Oneway', 'One-way'),
        ('Return', 'Return'),
    ]
    
    search_id = models.CharField(max_length=100, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='flight_searches')
    flight_search_type = models.CharField(max_length=10, choices=TRIP_TYPE_CHOICES)
    ticket_class = models.CharField(max_length=10, default='Y')
    adults = models.IntegerField(default=1)
    children = models.IntegerField(default=0)
    infants = models.IntegerField(default=0)
    departure_code = models.CharField(max_length=10)
    destination_code = models.CharField(max_length=10)
    departure_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.search_id} - {self.departure_code} to {self.destination_code}"
    
    def save(self, *args, **kwargs):
        if not self.search_id:
            self.search_id = self._generate_search_id()
        super().save(*args, **kwargs)
    
    @staticmethod
    def _generate_search_id():
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))


class FlightResult(models.Model):
    """Flight result from search"""
    search = models.ForeignKey(FlightSearch, on_delete=models.CASCADE, related_name='results')
    flight_id = models.CharField(max_length=100)
    connection_id = models.CharField(max_length=100)
    connection_code = models.CharField(max_length=100)
    price_amount = models.DecimalField(max_digits=12, decimal_places=2)
    price_currency = models.CharField(max_length=10, default='NGN')
    airline_code = models.CharField(max_length=10)
    airline_name = models.CharField(max_length=200)
    departure_code = models.CharField(max_length=10)
    departure_name = models.CharField(max_length=200)
    departure_time = models.DateTimeField()
    arrival_code = models.CharField(max_length=10)
    arrival_name = models.CharField(max_length=200)
    arrival_time = models.DateTimeField()
    stops = models.IntegerField(default=0)
    trip_duration = models.CharField(max_length=50)
    is_refundable = models.BooleanField(default=False)
    flight_data = models.JSONField(default=dict)  # Store full flight combination data
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.airline_code} {self.departure_code}-{self.arrival_code}"
    
    class Meta:
        ordering = ['price_amount']


class FlightLeg(models.Model):
    """Individual flight leg within a flight result"""
    flight_result = models.ForeignKey(FlightResult, on_delete=models.CASCADE, related_name='legs')
    leg_number = models.IntegerField()
    departure_code = models.CharField(max_length=10)
    departure_name = models.CharField(max_length=200)
    destination_code = models.CharField(max_length=10)
    destination_name = models.CharField(max_length=200)
    departure_date = models.DateField()
    departure_time = models.TimeField()
    arrival_date = models.DateField()
    arrival_time = models.TimeField()
    duration = models.CharField(max_length=50)
    is_stop = models.BooleanField(default=False)
    layover = models.CharField(max_length=100, null=True, blank=True)
    cabin_class = models.CharField(max_length=10)
    cabin_class_name = models.CharField(max_length=100)
    operating_carrier = models.CharField(max_length=10)
    marketing_carrier = models.CharField(max_length=10)
    flight_number = models.CharField(max_length=20)
    
    def __str__(self):
        return f"Leg {self.leg_number}: {self.departure_code}-{self.destination_code}"
    
    class Meta:
        ordering = ['leg_number']

