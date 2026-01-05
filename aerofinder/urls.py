from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="Aero Services API",
        default_version='v1',
        description="Aero Services",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path("schema/", schema_view.without_ui(cache_timeout=0), name="schema"),
    path('api/flights/', include('flights.urls')),  # Flights, airports
    path('api/', include('accounts.urls')),  # Users, registration
    path('api/', include('bookings.urls')),  # Bookings
    path('api/', include('wallets.urls')),  # Wallet, transactions
    path('api/', include('vouchers.urls')),  # Vouchers
    path('api/', include('audit.urls')),  # Audit logs
    path('accounts/search/', include('scraping.urls')),  # Legacy scraping endpoints
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
