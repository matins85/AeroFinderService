from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from accounts.managers import CustomUserManager


class CustomUser(AbstractUser):
    """Extended User model with agency and role support"""
    ROLE_CHOICES = [
        ('staff', 'Staff'),
        ('agent', 'Agent'),
        ('admin', 'Admin'),
    ]
    
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='agent')
    is_master_agent = models.BooleanField(default=False)
    master_agent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sub_agents'
    )
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    objects = CustomUserManager()
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'


class Agency(models.Model):
    """Agency information linked to user"""
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='agency')
    agency_name = models.CharField(max_length=200)
    agency_email = models.EmailField()
    agency_address = models.TextField()
    agency_phone = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.agency_name

