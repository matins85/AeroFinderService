from django.db import models
from django.conf import settings
from flights.models import FlightResult
import random
import string


class Booking(models.Model):
    """Booking record"""
    TRIP_TYPE_CHOICES = [
        ('One-way', 'One-way'),
        ('Return', 'Return'),
        ('Multi-City', 'Multi-City'),
    ]
    
    STATUS_CHOICES = [
        ('Issued', 'Issued'),
        ('Pending', 'Pending'),
        ('Cancelled', 'Cancelled'),
    ]
    
    PNR_STATUS_CHOICES = [
        ('Issued', 'Issued'),
        ('—', '—'),
    ]
    
    REISSUE_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Completed', 'Completed'),
    ]
    
    booking_id = models.CharField(max_length=50, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    flight_result = models.ForeignKey(FlightResult, on_delete=models.PROTECT, related_name='bookings')
    trip_type = models.CharField(max_length=20, choices=TRIP_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50)  # 'paystack' or 'wallet'
    payment_reference = models.CharField(max_length=100, null=True, blank=True, db_index=True)  # Paystack reference
    payment_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ])
    pnr = models.CharField(max_length=20, null=True, blank=True)
    pnr_status = models.CharField(max_length=20, choices=PNR_STATUS_CHOICES, null=True, blank=True)
    reissue_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reissue_status = models.CharField(max_length=20, choices=REISSUE_STATUS_CHOICES, null=True, blank=True)
    booking_date = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.booking_id} - {self.user.email}"
    
    def save(self, *args, **kwargs):
        if not self.booking_id:
            self.booking_id = self._generate_booking_id()
        super().save(*args, **kwargs)
    
    @staticmethod
    def _generate_booking_id():
        """Generate booking ID in format BK-XXXXX"""
        number = ''.join(random.choices(string.digits, k=5))
        return f"BK-{number}"


class Passenger(models.Model):
    """Passenger information for booking"""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='passengers')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    passport_number = models.CharField(max_length=50, null=True, blank=True)
    nin = models.CharField(max_length=50, null=True, blank=True)
    bvn = models.CharField(max_length=50, null=True, blank=True)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.booking.booking_id}"

