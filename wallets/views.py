import random
import string
from decimal import Decimal

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Wallet, Transaction, WithdrawalRequest
from .serializers import WalletSerializer, TransactionSerializer, WithdrawalRequestSerializer
from .services import create_virtual_account_for_user
from audit.models import AuditLog


class WalletViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for wallet management"""
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Wallet.objects.filter(user=self.request.user)
    
    def get_object(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet
    
    @action(detail=False, methods=['post'], url_path='top-up')
    def top_up(self, request):
        """Top up wallet"""
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        amount = Decimal(str(request.data.get('amount', 0)))
        payment_method = request.data.get('paymentMethod', '')
        
        if amount <= 0:
            return Response(
                {'error': 'Amount must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create transaction
        transaction = Transaction.objects.create(
            wallet=wallet,
            type='credit',
            amount=amount,
            description=f'Wallet top-up via {payment_method}',
            status='completed',
            reference=self._generate_reference()
        )
        
        # Update wallet balance
        wallet.balance += amount
        wallet.save()
        
        # Create audit log
        AuditLog.objects.create(
            user=request.user,
            action='WALLET_TOP_UP',
            resource_type='Transaction',
            resource_id=str(transaction.id),
            description=f'Topped up wallet with {amount}',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response(TransactionSerializer(transaction).data)
    
    @action(detail=False, methods=['post'], url_path='withdraw')
    def withdraw(self, request):
        """Request withdrawal"""
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        amount = Decimal(str(request.data.get('amount', 0)))
        bank_name = request.data.get('bankName', '')
        account_number = request.data.get('accountNumber', '')
        
        if amount <= 0:
            return Response(
                {'error': 'Amount must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if wallet.balance < amount:
            return Response(
                {'error': 'Insufficient balance'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate OTP (in production, send via SMS/Email)
        otp_code = ''.join(random.choices(string.digits, k=6))
        
        withdrawal = WithdrawalRequest.objects.create(
            user=request.user,
            amount=amount,
            bank_name=bank_name,
            account_number=account_number,
            account_name='',  # Should be fetched from bank API
            otp_code=otp_code,
            status='pending'
        )
        
        # Create audit log
        AuditLog.objects.create(
            user=request.user,
            action='WITHDRAWAL_REQUEST',
            resource_type='WithdrawalRequest',
            resource_id=str(withdrawal.id),
            description=f'Requested withdrawal of {amount}',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response({
            'accountName': withdrawal.account_name or 'Pending verification',
            'withdrawalId': withdrawal.id
        })
    
    @action(detail=False, methods=['post'], url_path='withdraw/(?P<withdrawal_id>[^/.]+)/verify-otp')
    def verify_otp(self, request, withdrawal_id=None):
        """Verify OTP and process withdrawal"""
        try:
            withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id, user=request.user)
        except WithdrawalRequest.DoesNotExist:
            return Response(
                {'error': 'Withdrawal request not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        otp_code = request.data.get('otpCode', '')
        
        if withdrawal.otp_code != otp_code:
            return Response(
                {'error': 'Invalid OTP code'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        withdrawal.otp_verified = True
        withdrawal.status = 'processing'
        withdrawal.save()
        
        # Create debit transaction
        wallet = request.user.wallet
        transaction = Transaction.objects.create(
            wallet=wallet,
            type='debit',
            amount=withdrawal.amount,
            description=f'Withdrawal to {withdrawal.bank_name} - {withdrawal.account_number}',
            status='pending',
            reference=self._generate_reference()
        )
        
        # Update wallet balance
        wallet.balance -= withdrawal.amount
        wallet.save()
        
        # In production, initiate bank transfer here
        # For now, mark as completed
        withdrawal.status = 'completed'
        withdrawal.processed_at = timezone.now()
        withdrawal.save()
        
        transaction.status = 'completed'
        transaction.save()
        
        # Create audit log
        AuditLog.objects.create(
            user=request.user,
            action='WITHDRAWAL_COMPLETED',
            resource_type='WithdrawalRequest',
            resource_id=str(withdrawal.id),
            description=f'Completed withdrawal of {withdrawal.amount}',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response({'status': withdrawal.status})
    
    @action(detail=False, methods=['post'], url_path='create-virtual-account')
    def create_virtual_account(self, request):
        """Manually create virtual account (admin only or retry)"""
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        if wallet.virtual_account_created:
            return Response(
                {'message': 'Virtual account already exists', 'wallet': WalletSerializer(wallet).data},
                status=status.HTTP_200_OK
            )
        
        # Create virtual account
        success, error_message, account_data = create_virtual_account_for_user(request.user)
        
        if success and account_data:
            wallet.virtual_account_number = account_data['virtual_account_number']
            wallet.virtual_account_bank = account_data['virtual_account_bank']
            wallet.virtual_account_name = account_data['virtual_account_name']
            wallet.virtual_account_reference = account_data['virtual_account_reference']
            wallet.virtual_account_created = True
            wallet.virtual_account_creation_error = None
            wallet.save()
            
            # Create audit log
            AuditLog.objects.create(
                user=request.user,
                action='CREATE_VIRTUAL_ACCOUNT',
                resource_type='Wallet',
                resource_id=str(wallet.id),
                description=f'Created virtual account for {request.user.email}',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response(
                {'message': 'Virtual account created successfully', 'wallet': WalletSerializer(wallet).data},
                status=status.HTTP_201_CREATED
            )
        else:
            wallet.virtual_account_creation_error = error_message
            wallet.save()
            
            return Response(
                {'error': 'Failed to create virtual account', 'details': error_message},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @staticmethod
    def _generate_reference():
        """Generate unique reference"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    
    @staticmethod
    def _get_client_ip(request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for transaction history"""
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return Transaction.objects.filter(wallet=wallet).order_by('-created_at')

