from django.contrib import admin
from .models import Voucher, VoucherUser, VoucherUsage


class VoucherUserInline(admin.TabularInline):
    """Inline admin for VoucherUser"""
    model = VoucherUser
    extra = 0
    fields = ['user']


class VoucherUsageInline(admin.TabularInline):
    """Inline admin for VoucherUsage"""
    model = VoucherUsage
    extra = 0
    readonly_fields = ['user', 'booking', 'used_at']
    can_delete = False


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    """Admin configuration for Voucher"""
    list_display = ['code', 'type', 'value', 'status', 'usage_limit', 'used_count', 
                    'start_date', 'end_date', 'created_by', 'created_at']
    list_filter = ['type', 'status', 'target_users', 'start_date', 'end_date', 'created_at']
    search_fields = ['code', 'voucher_id', 'description', 'created_by__email']
    readonly_fields = ['voucher_id', 'created_at', 'updated_at']
    inlines = [VoucherUserInline, VoucherUsageInline]
    
    fieldsets = (
        ('Voucher Information', {
            'fields': ('voucher_id', 'code', 'type', 'value', 'status')
        }),
        ('Usage Limits', {
            'fields': ('usage_limit', 'used_count', 'min_purchase', 'max_discount')
        }),
        ('Validity Period', {
            'fields': ('start_date', 'end_date')
        }),
        ('Target Users', {
            'fields': ('target_users', 'created_by')
        }),
        ('Description', {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(VoucherUser)
class VoucherUserAdmin(admin.ModelAdmin):
    """Admin configuration for VoucherUser"""
    list_display = ['voucher', 'user', 'created_at']
    list_filter = ['created_at', 'voucher__status']
    search_fields = ['voucher__code', 'user__email']


@admin.register(VoucherUsage)
class VoucherUsageAdmin(admin.ModelAdmin):
    """Admin configuration for VoucherUsage"""
    list_display = ['voucher', 'user', 'booking', 'used_at']
    list_filter = ['used_at', 'voucher__code']
    search_fields = ['voucher__code', 'user__email', 'booking__booking_id']
    readonly_fields = ['used_at']

