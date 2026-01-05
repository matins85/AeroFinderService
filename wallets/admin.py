from django.contrib import admin
from .models import Wallet, Transaction, WithdrawalRequest


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    """Admin configuration for Wallet"""
    list_display = ['user', 'balance', 'virtual_account_number', 'virtual_account_bank',
                    'virtual_account_created', 'created_at']
    list_filter = ['virtual_account_created', 'created_at', 'updated_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 
                     'virtual_account_number', 'virtual_account_reference']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Wallet Information', {
            'fields': ('user', 'balance')
        }),
        ('Virtual Account', {
            'fields': ('virtual_account_number', 'virtual_account_bank', 'virtual_account_name',
                      'virtual_account_reference', 'virtual_account_created', 'virtual_account_creation_error')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin configuration for Transaction"""
    list_display = ['transaction_id', 'wallet', 'type', 'amount', 'status', 
                    'description', 'agent', 'created_at']
    list_filter = ['type', 'status', 'created_at']
    search_fields = ['transaction_id', 'reference', 'wallet__user__email', 
                     'description', 'agent__email']
    readonly_fields = ['transaction_id', 'reference', 'created_at']
    
    fieldsets = (
        ('Transaction Information', {
            'fields': ('transaction_id', 'wallet', 'type', 'amount', 'status', 'reference')
        }),
        ('Details', {
            'fields': ('description', 'agent')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    """Admin configuration for WithdrawalRequest"""
    list_display = ['user', 'amount', 'bank_name', 'account_number', 'status', 
                    'otp_verified', 'created_at', 'processed_at']
    list_filter = ['status', 'otp_verified', 'created_at', 'processed_at']
    search_fields = ['user__email', 'bank_name', 'account_number', 'account_name']
    readonly_fields = ['created_at', 'processed_at']
    
    fieldsets = (
        ('Withdrawal Information', {
            'fields': ('user', 'amount', 'status')
        }),
        ('Bank Details', {
            'fields': ('bank_name', 'account_number', 'account_name')
        }),
        ('OTP Verification', {
            'fields': ('otp_code', 'otp_verified'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'processed_at'),
            'classes': ('collapse',)
        }),
    )

