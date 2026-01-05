from rest_framework import serializers
from .models import Wallet, Transaction, WithdrawalRequest


class TransactionSerializer(serializers.ModelSerializer):
    transactionId = serializers.CharField(source='transaction_id', read_only=True)
    date = serializers.DateField(source='created_at', read_only=True)
    time = serializers.TimeField(source='created_at', read_only=True)
    agent = serializers.CharField(source='agent.email', read_only=True, allow_null=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'transactionId', 'type', 'amount', 'description', 'date',
            'time', 'status', 'reference', 'agent'
        ]


class WalletSerializer(serializers.ModelSerializer):
    transactions = TransactionSerializer(many=True, read_only=True)
    virtualAccountNumber = serializers.CharField(source='virtual_account_number', read_only=True)
    virtualAccountBank = serializers.CharField(source='virtual_account_bank', read_only=True)
    virtualAccountName = serializers.CharField(source='virtual_account_name', read_only=True)
    virtualAccountReference = serializers.CharField(source='virtual_account_reference', read_only=True)
    hasVirtualAccount = serializers.BooleanField(source='has_virtual_account', read_only=True)
    virtualAccountCreated = serializers.BooleanField(source='virtual_account_created', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    
    class Meta:
        model = Wallet
        fields = [
            'id', 'balance', 'transactions', 
            'virtualAccountNumber', 'virtualAccountBank', 'virtualAccountName',
            'virtualAccountReference', 'hasVirtualAccount', 'virtualAccountCreated',
            'createdAt', 'updatedAt'
        ]


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    withdrawalId = serializers.IntegerField(source='id', read_only=True)
    accountName = serializers.CharField(source='account_name', read_only=True)
    otpCode = serializers.CharField(source='otp_code', write_only=True, required=False)
    
    class Meta:
        model = WithdrawalRequest
        fields = [
            'withdrawalId', 'amount', 'bank_name', 'account_number',
            'accountName', 'otpCode', 'status', 'created_at'
        ]
        read_only_fields = ['accountName', 'status', 'created_at']

