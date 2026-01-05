from django.db import models
from django.conf import settings
from django.utils import timezone
import random
import string


class Voucher(models.Model):
    """Voucher/Discount code"""
    TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
        ('used', 'Used'),
    ]
    
    TARGET_USERS_CHOICES = [
        ('all', 'All Users'),
        ('specific', 'Specific Users'),
    ]
    
    voucher_id = models.CharField(max_length=50, unique=True, db_index=True)
    code = models.CharField(max_length=50, unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    min_purchase = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_discount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    usage_limit = models.IntegerField(default=1)
    used_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    start_date = models.DateField()
    end_date = models.DateField()
    description = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_vouchers')
    target_users = models.CharField(max_length=20, choices=TARGET_USERS_CHOICES, default='all')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.code} - {self.type} - {self.value}"
    
    def save(self, *args, **kwargs):
        if not self.voucher_id:
            self.voucher_id = self._generate_voucher_id()
        super().save(*args, **kwargs)
    
    @staticmethod
    def _generate_voucher_id():
        """Generate voucher ID in format VCH-XXXXX"""
        number = ''.join(random.choices(string.digits, k=5))
        return f"VCH-{number}"
    
    def is_valid(self):
        """Check if voucher is valid"""
        now = timezone.now().date()
        return (
            self.status == 'active' and
            self.start_date <= now <= self.end_date and
            self.used_count < self.usage_limit
        )


class VoucherUser(models.Model):
    """Users assigned to specific voucher"""
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='voucher_users')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_vouchers')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['voucher', 'user']
    
    def __str__(self):
        return f"{self.voucher.code} - {self.user.email}"


class VoucherUsage(models.Model):
    """Voucher usage tracking"""
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='voucher_usages')
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='voucher_usage')
    used_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.voucher.code} used by {self.user.email}"

