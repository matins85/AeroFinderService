from django.contrib import admin
from .models import Airport, FlightSearch, FlightResult, FlightLeg


@admin.register(Airport)
class AirportAdmin(admin.ModelAdmin):
    """Admin configuration for Airport"""
    list_display = ['airport_code', 'description', 'city', 'country', 'priority']
    list_filter = ['country', 'priority']
    search_fields = ['airport_code', 'description', 'city', 'country', 'city_country']
    ordering = ['-priority', 'airport_code']


class FlightLegInline(admin.TabularInline):
    """Inline admin for FlightLeg"""
    model = FlightLeg
    extra = 0
    readonly_fields = ['leg_number', 'departure_code', 'departure_name', 'destination_code', 
                       'destination_name', 'departure_date', 'departure_time', 'arrival_date', 
                       'arrival_time', 'duration', 'is_stop', 'layover', 'cabin_class', 
                       'cabin_class_name', 'operating_carrier', 'marketing_carrier', 'flight_number']


@admin.register(FlightResult)
class FlightResultAdmin(admin.ModelAdmin):
    """Admin configuration for FlightResult"""
    list_display = ['flight_id', 'airline_name', 'departure_code', 'arrival_code', 
                    'price_amount', 'price_currency', 'departure_time', 'created_at']
    list_filter = ['airline_code', 'price_currency', 'is_refundable', 'created_at']
    search_fields = ['flight_id', 'airline_name', 'departure_code', 'arrival_code', 
                     'connection_id', 'connection_code']
    readonly_fields = ['created_at']
    inlines = [FlightLegInline]
    
    fieldsets = (
        ('Flight Information', {
            'fields': ('search', 'flight_id', 'connection_id', 'connection_code', 'airline_code', 'airline_name')
        }),
        ('Route Information', {
            'fields': ('departure_code', 'departure_name', 'departure_time', 
                      'arrival_code', 'arrival_name', 'arrival_time', 'stops', 'trip_duration')
        }),
        ('Pricing', {
            'fields': ('price_amount', 'price_currency', 'is_refundable')
        }),
        ('Additional Data', {
            'fields': ('flight_data', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(FlightSearch)
class FlightSearchAdmin(admin.ModelAdmin):
    """Admin configuration for FlightSearch"""
    list_display = ['search_id', 'user', 'flight_search_type', 'departure_code', 
                    'destination_code', 'departure_date', 'created_at']
    list_filter = ['flight_search_type', 'ticket_class', 'departure_date', 'created_at']
    search_fields = ['search_id', 'user__email', 'departure_code', 'destination_code']
    readonly_fields = ['search_id', 'created_at']
    
    fieldsets = (
        ('Search Information', {
            'fields': ('search_id', 'user', 'flight_search_type', 'ticket_class')
        }),
        ('Passengers', {
            'fields': ('adults', 'children', 'infants')
        }),
        ('Route', {
            'fields': ('departure_code', 'destination_code', 'departure_date', 'return_date')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

