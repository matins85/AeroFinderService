from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VoucherViewSet

router = DefaultRouter()
router.register(r'vouchers', VoucherViewSet, basename='voucher')

urlpatterns = [
    path('', include(router.urls)),
]

