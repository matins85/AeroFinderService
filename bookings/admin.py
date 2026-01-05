from django.contrib import admin
from .models import Booking, Passenger


class PassengerInline(admin.TabularInline):
    """Inline admin for Passenger"""
    model = Passenger
    extra = 0
    fields = ['first_name', 'last_name', 'date_of_birth', 'email', 'phone', 
              'passport_number', 'nin', 'bvn']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Admin configuration for Booking"""
    list_display = ['booking_id', 'user', 'trip_type', 'status', 'amount', 
                    'payment_method', 'pnr', 'pnr_status', 'booking_date']
    list_filter = ['status', 'trip_type', 'pnr_status', 'reissue_status', 'booking_date', 'created_at']
    search_fields = ['booking_id', 'user__email', 'pnr', 'flight_result__airline_name']
    readonly_fields = ['booking_id', 'booking_date', 'created_at', 'updated_at']
    inlines = [PassengerInline]
    
    fieldsets = (
        ('Booking Information', {
            'fields': ('booking_id', 'user', 'flight_result', 'trip_type', 'status', 'booking_date')
        }),
        ('Payment', {
            'fields': ('amount', 'payment_method')
        }),
        ('PNR Information', {
            'fields': ('pnr', 'pnr_status')
        }),
        ('Reissue Information', {
            'fields': ('reissue_amount', 'reissue_status'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Passenger)
class PassengerAdmin(admin.ModelAdmin):
    """Admin configuration for Passenger"""
    list_display = ['first_name', 'last_name', 'booking', 'email', 'phone', 'date_of_birth']
    list_filter = ['booking__status', 'booking__booking_date']
    search_fields = ['first_name', 'last_name', 'email', 'phone', 'passport_number', 
                     'nin', 'bvn', 'booking__booking_id']
    
    fieldsets = (
        ('Passenger Information', {
            'fields': ('booking', 'first_name', 'last_name', 'date_of_birth', 'email', 'phone')
        }),
        ('Identification', {
            'fields': ('passport_number', 'nin', 'bvn'),
            'classes': ('collapse',)
        }),
    )

