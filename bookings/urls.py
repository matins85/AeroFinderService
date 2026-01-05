from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BookingViewSet, PaystackWebhookView

router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('bookings/payment/webhook/', PaystackWebhookView.as_view(), name='paystack-webhook'),
    path('', include(router.urls)),
]

