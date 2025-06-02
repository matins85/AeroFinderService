from django.contrib.auth.models import AbstractUser
from django.db import models
from accounts.managers import RAUserManager


class RAUser(AbstractUser):
    username = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []
    objects = RAUserManager()
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)
