from django.db import models
from django.conf import settings
import random
import string


class Wallet(models.Model):
    """User wallet for managing balance"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Virtual Account fields
    virtual_account_number = models.CharField(max_length=20, null=True, blank=True, unique=True, db_index=True)
    virtual_account_bank = models.CharField(max_length=100, null=True, blank=True)
    virtual_account_name = models.CharField(max_length=200, null=True, blank=True)
    virtual_account_reference = models.CharField(max_length=100, null=True, blank=True, unique=True, db_index=True)
    virtual_account_created = models.BooleanField(default=False)
    virtual_account_creation_error = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.balance}"
    
    @property
    def has_virtual_account(self):
        """Check if wallet has a virtual account"""
        return self.virtual_account_created and self.virtual_account_number is not None


class Transaction(models.Model):
    """Wallet transaction"""
    TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
        ('pending', 'Pending'),
    ]
    
    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    ]
    
    transaction_id = models.CharField(max_length=50, unique=True, db_index=True)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reference = models.CharField(max_length=100, unique=True)
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.transaction_id} - {self.type} - {self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = self._generate_transaction_id()
        if not self.reference:
            self.reference = self._generate_reference()
        super().save(*args, **kwargs)
    
    @staticmethod
    def _generate_transaction_id():
        """Generate transaction ID in format TXN-XXXXX"""
        number = ''.join(random.choices(string.digits, k=5))
        return f"TXN-{number}"
    
    @staticmethod
    def _generate_reference():
        """Generate unique reference"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))


class WithdrawalRequest(models.Model):
    """Withdrawal request from wallet"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    bank_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=200)
    otp_code = models.CharField(max_length=10, null=True, blank=True)
    otp_verified = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.amount} - {self.status}"

