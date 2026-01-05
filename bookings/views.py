from decimal import Decimal
import random
import string
import logging

from django.db.models import Q
from django.db import transaction as db_transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json

from .models import Booking, Passenger
from .serializers import BookingSerializer, BookingCreateSerializer, PassengerSerializer
from .services import PaystackService
from flights.models import FlightResult
from vouchers.models import Voucher, VoucherUser, VoucherUsage
from wallets.models import Wallet, Transaction
from audit.models import AuditLog

logger = logging.getLogger(__name__)


class BookingViewSet(viewsets.ModelViewSet):
    """ViewSet for booking management"""
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status']
    search_fields = ['booking_id', 'pnr', 'flight_result__airline_name']
    
    def get_queryset(self):
        queryset = Booking.objects.filter(user=self.request.user)
        status_filter = self.request.query_params.get('status')
        search = self.request.query_params.get('search')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if search:
            queryset = queryset.filter(
                Q(booking_id__icontains=search) |
                Q(pnr__icontains=search) |
                Q(flight_result__airline_name__icontains=search)
            )
        
        return queryset.select_related('flight_result', 'user').prefetch_related('passengers')
    
    def create(self, request, *args, **kwargs):
        """Create a new booking"""
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        flight_result_id = serializer.validated_data['flight_result_id']
        try:
            flight_result = FlightResult.objects.get(id=flight_result_id)
        except FlightResult.DoesNotExist:
            return Response(
                {'error': 'Flight result not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Calculate amount (apply voucher if provided)
        amount = flight_result.price_amount
        voucher_code = serializer.validated_data.get('voucherCode')
        discount_amount = Decimal('0')
        
        if voucher_code:
            voucher_result = self._validate_voucher(voucher_code, amount, request.user)
            if voucher_result['valid']:
                discount_amount = voucher_result['discountAmount']
                amount = amount - discount_amount
        
        payment_method = serializer.validated_data['payment_method']
        
        # Generate payment reference
        payment_reference = self._generate_payment_reference()
        
        # Handle wallet payment
        if payment_method == 'wallet':
            wallet, _ = Wallet.objects.get_or_create(user=request.user)
            
            if wallet.balance < amount:
                return Response(
                    {'error': 'Insufficient wallet balance'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create booking with wallet payment
            with db_transaction.atomic():
                booking = Booking.objects.create(
                    user=request.user,
                    flight_result=flight_result,
                    trip_type=serializer.validated_data['tripType'],
                    amount=amount,
                    payment_method=payment_method,
                    payment_reference=payment_reference,
                    payment_status='success',
                    status='Pending'
                )
                
                # Create passengers
                for passenger_data in serializer.validated_data['passengers']:
                    Passenger.objects.create(
                        booking=booking,
                        **passenger_data
                    )
                
                # Deduct from wallet
                wallet.balance -= amount
                wallet.save()
                
                # Create transaction record
                Transaction.objects.create(
                    wallet=wallet,
                    type='debit',
                    amount=amount,
                    description=f'Booking payment for {booking.booking_id}',
                    status='completed',
                    reference=payment_reference
                )
                
                # Record voucher usage if applicable
                if voucher_code and discount_amount > 0:
                    try:
                        voucher = Voucher.objects.get(code=voucher_code)
                        VoucherUsage.objects.create(
                            voucher=voucher,
                            user=request.user,
                            booking=booking
                        )
                        voucher.used_count += 1
                        voucher.save()
                    except Voucher.DoesNotExist:
                        pass
                
                # Create audit log
                AuditLog.objects.create(
                    user=request.user,
                    action='CREATE_BOOKING',
                    resource_type='Booking',
                    resource_id=str(booking.id),
                    description=f'Created booking {booking.booking_id} with wallet payment',
                    ip_address=self._get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            
            return Response(
                BookingSerializer(booking).data,
                status=status.HTTP_201_CREATED
            )
        
        # Handle Paystack payment
        elif payment_method == 'paystack':
            # Get customer email from first passenger or user email
            passengers_data = serializer.validated_data['passengers']
            if passengers_data and len(passengers_data) > 0:
                # Access email from passenger dict (serializer returns dict)
                customer_email = passengers_data[0].get('email', request.user.email)
            else:
                customer_email = request.user.email
            
            # Initialize Paystack transaction
            paystack_service = PaystackService()
            callback_url = request.data.get('callback_url') or f"{request.build_absolute_uri('/')}api/bookings/payment/callback"
            
            metadata = {
                'booking_user_id': str(request.user.id),
                'flight_result_id': str(flight_result_id),
                'trip_type': serializer.validated_data['tripType'],
            }
            
            paystack_response = paystack_service.initialize_transaction(
                email=customer_email,
                amount=amount,
                reference=payment_reference,
                callback_url=callback_url,
                metadata=metadata
            )
            
            if not paystack_response.get('status'):
                return Response(
                    {'error': 'Failed to initialize payment', 'details': paystack_response.get('message')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create booking with pending payment
            with db_transaction.atomic():
                booking = Booking.objects.create(
                    user=request.user,
                    flight_result=flight_result,
                    trip_type=serializer.validated_data['tripType'],
                    amount=amount,
                    payment_method=payment_method,
                    payment_reference=payment_reference,
                    payment_status='pending',
                    status='Pending'
                )
                
                # Create passengers
                for passenger_data in serializer.validated_data['passengers']:
                    Passenger.objects.create(
                        booking=booking,
                        **passenger_data
                    )
                
                # Create audit log
                AuditLog.objects.create(
                    user=request.user,
                    action='CREATE_BOOKING',
                    resource_type='Booking',
                    resource_id=str(booking.id),
                    description=f'Created booking {booking.booking_id} with Paystack payment',
                    ip_address=self._get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            
            # Return booking with Paystack authorization URL
            booking_data = BookingSerializer(booking).data
            booking_data['payment'] = {
                'authorization_url': paystack_response['data']['authorization_url'],
                'access_code': paystack_response['data']['access_code'],
                'reference': payment_reference
            }
            
            return Response(
                booking_data,
                status=status.HTTP_201_CREATED
            )
        
        else:
            return Response(
                {'error': 'Invalid payment method. Use "paystack" or "wallet"'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['patch'], url_path='cancel')
    def cancel(self, request, pk=None):
        """Cancel a booking"""
        booking = self.get_object()
        
        if booking.status == 'Cancelled':
            return Response(
                {'error': 'Booking is already cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'Cancelled'
        booking.save()
        
        # Create audit log
        AuditLog.objects.create(
            user=request.user,
            action='CANCEL_BOOKING',
            resource_type='Booking',
            resource_id=str(booking.id),
            description=f'Cancelled booking {booking.booking_id}',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response(BookingSerializer(booking).data)
    
    def _validate_voucher(self, code, amount, user):
        """Validate voucher and calculate discount"""
        try:
            voucher = Voucher.objects.get(code=code)
        except Voucher.DoesNotExist:
            return {'valid': False, 'discountAmount': None, 'message': 'Invalid voucher code'}
        
        if not voucher.is_valid():
            return {'valid': False, 'discountAmount': None, 'message': 'Voucher is expired or inactive'}
        
        # Check if user is eligible
        if voucher.target_users == 'specific':
            if not VoucherUser.objects.filter(voucher=voucher, user=user).exists():
                return {'valid': False, 'discountAmount': None, 'message': 'Voucher not applicable to this user'}
        
        # Check minimum purchase
        if voucher.min_purchase and amount < voucher.min_purchase:
            return {
                'valid': False,
                'discountAmount': None,
                'message': f'Minimum purchase of {voucher.min_purchase} required'
            }
        
        # Calculate discount
        if voucher.type == 'percentage':
            discount = (amount * voucher.value) / 100
            if voucher.max_discount:
                discount = min(discount, voucher.max_discount)
        else:  # fixed
            discount = voucher.value
        
        return {
            'valid': True,
            'discountAmount': discount,
            'message': 'Voucher is valid'
        }
    
    @action(detail=True, methods=['post'], url_path='verify-payment')
    def verify_payment(self, request, pk=None):
        """Verify Paystack payment for a booking"""
        booking = self.get_object()
        
        if booking.payment_method != 'paystack':
            return Response(
                {'error': 'This booking does not use Paystack payment'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not booking.payment_reference:
            return Response(
                {'error': 'Payment reference not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify payment with Paystack
        paystack_service = PaystackService()
        verification_response = paystack_service.verify_transaction(booking.payment_reference)
        
        if not verification_response.get('status'):
            return Response(
                {'error': 'Payment verification failed', 'details': verification_response.get('message')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        transaction_data = verification_response.get('data', {})
        
        # Update booking payment status
        if transaction_data.get('status') == 'success':
            booking.payment_status = 'success'
            booking.status = 'Pending'  # Ready for ticket issuance
            booking.save()
            
            # Record voucher usage if applicable
            voucher_code = request.data.get('voucherCode')
            if voucher_code:
                try:
                    voucher = Voucher.objects.get(code=voucher_code)
                    VoucherUsage.objects.get_or_create(
                        voucher=voucher,
                        user=request.user,
                        booking=booking
                    )
                    voucher.used_count += 1
                    voucher.save()
                except Voucher.DoesNotExist:
                    pass
            
            # Create audit log
            AuditLog.objects.create(
                user=request.user,
                action='PAYMENT_VERIFIED',
                resource_type='Booking',
                resource_id=str(booking.id),
                description=f'Payment verified for booking {booking.booking_id}',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({
                'status': 'success',
                'message': 'Payment verified successfully',
                'booking': BookingSerializer(booking).data
            })
        else:
            booking.payment_status = 'failed'
            booking.save()
            
            return Response({
                'status': 'failed',
                'message': 'Payment verification failed',
                'booking': BookingSerializer(booking).data
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @staticmethod
    def _generate_payment_reference():
        """Generate unique payment reference"""
        return f"BK-{''.join(random.choices(string.ascii_uppercase + string.digits, k=16))}"
    
    @staticmethod
    def _get_client_ip(request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    """Webhook endpoint for Paystack payment callbacks"""
    permission_classes = []  # No authentication required for webhooks
    
    def post(self, request):
        """Handle Paystack webhook"""
        # Get signature from header
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
        
        # Get raw body
        payload = request.body.decode('utf-8')
        
        # Verify webhook signature
        paystack_service = PaystackService()
        if not paystack_service.verify_webhook(payload, signature):
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse webhook data
        try:
            webhook_data = json.loads(payload)
            event = webhook_data.get('event')
            data = webhook_data.get('data', {})
            
            if event == 'charge.success':
                reference = data.get('reference')
                
                try:
                    booking = Booking.objects.get(payment_reference=reference)
                    
                    # Update booking status
                    booking.payment_status = 'success'
                    booking.status = 'Pending'  # Ready for ticket issuance
                    booking.save()
                    
                    # Create audit log
                    AuditLog.objects.create(
                        user=booking.user,
                        action='PAYMENT_SUCCESS_WEBHOOK',
                        resource_type='Booking',
                        resource_id=str(booking.id),
                        description=f'Payment successful via webhook for booking {booking.booking_id}',
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    return Response({'status': 'success'})
                except Booking.DoesNotExist:
                    return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
            
            elif event == 'charge.failed':
                reference = data.get('reference')
                
                try:
                    booking = Booking.objects.get(payment_reference=reference)
                    booking.payment_status = 'failed'
                    booking.save()
                    
                    return Response({'status': 'success'})
                except Booking.DoesNotExist:
                    return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
            
            elif event == 'transfer.success':
                # Handle virtual account transfer (money deposited into virtual account)
                account_number = data.get('recipient', {}).get('account_number') or data.get('account', {}).get('account_number')
                amount = data.get('amount', 0) / 100  # Convert from kobo to NGN
                reference = data.get('reference')
                
                if account_number:
                    try:
                        from wallets.models import Wallet
                        wallet = Wallet.objects.get(virtual_account_number=account_number)
                        
                        # Credit wallet
                        wallet.balance += Decimal(str(amount))
                        wallet.save()
                        
                        # Create transaction record
                        from wallets.models import Transaction
                        Transaction.objects.create(
                            wallet=wallet,
                            type='credit',
                            amount=Decimal(str(amount)),
                            description=f'Virtual account deposit - {reference}',
                            status='completed',
                            reference=reference
                        )
                        
                        # Create audit log
                        AuditLog.objects.create(
                            user=wallet.user,
                            action='VIRTUAL_ACCOUNT_DEPOSIT',
                            resource_type='Wallet',
                            resource_id=str(wallet.id),
                            description=f'Deposit of {amount} to virtual account {account_number}',
                            ip_address=request.META.get('REMOTE_ADDR'),
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        return Response({'status': 'success'})
                    except Wallet.DoesNotExist:
                        logger.warning(f"Virtual account {account_number} not found for transfer")
                        return Response({'error': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
            
            return Response({'status': 'success'})
            
        except json.JSONDecodeError:
            return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)


