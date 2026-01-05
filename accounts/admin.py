from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import CustomUser, Agency


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    """Admin configuration for CustomUser"""
    list_display = ['email', 'first_name', 'last_name', 'role', 'is_master_agent', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active', 'is_master_agent', 'date_joined']
    search_fields = ['email', 'first_name', 'last_name', 'phone_number']
    ordering = ['-date_joined']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Additional Information', {
            'fields': ('phone_number', 'role', 'is_master_agent', 'master_agent')
        }),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Additional Information', {
            'fields': ('email', 'first_name', 'last_name', 'phone_number',
                       'role', 'is_master_agent', 'is_staff', "is_active", 'date_joined',
                       'is_superuser', 'groups', 'user_permissions'),
        }),
    )


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    """Admin configuration for Agency"""
    list_display = ['agency_name', 'user', 'agency_email', 'agency_phone', 'created_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['agency_name', 'agency_email', 'agency_phone', 'user__email']
    readonly_fields = ['created_at', 'updated_at']

