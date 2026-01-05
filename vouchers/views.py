from decimal import Decimal

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import filters

from .models import Voucher, VoucherUser
from .serializers import VoucherSerializer


class VoucherViewSet(viewsets.ModelViewSet):
    """ViewSet for voucher management"""
    queryset = Voucher.objects.all()
    serializer_class = VoucherSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status']
    search_fields = ['code', 'description']
    
    @action(detail=False, methods=['get'], url_path='validate', permission_classes=[IsAuthenticated])
    def validate_voucher(self, request):
        """Validate a voucher code"""
        code = request.query_params.get('code')
        amount = Decimal(str(request.query_params.get('amount', 0)))
        
        if not code:
            return Response(
                {'valid': False, 'discountAmount': None, 'message': 'Voucher code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            voucher = Voucher.objects.get(code=code)
        except Voucher.DoesNotExist:
            return Response({
                'valid': False,
                'discountAmount': None,
                'message': 'Invalid voucher code'
            })
        
        if not voucher.is_valid():
            return Response({
                'valid': False,
                'discountAmount': None,
                'message': 'Voucher is expired or inactive'
            })
        
        # Check if user is eligible
        if voucher.target_users == 'specific':
            if not VoucherUser.objects.filter(voucher=voucher, user=request.user).exists():
                return Response({
                    'valid': False,
                    'discountAmount': None,
                    'message': 'Voucher not applicable to this user'
                })
        
        # Check minimum purchase
        if voucher.min_purchase and amount < voucher.min_purchase:
            return Response({
                'valid': False,
                'discountAmount': None,
                'message': f'Minimum purchase of {voucher.min_purchase} required'
            })
        
        # Calculate discount
        if voucher.type == 'percentage':
            discount = (amount * voucher.value) / 100
            if voucher.max_discount:
                discount = min(discount, voucher.max_discount)
        else:  # fixed
            discount = voucher.value
        
        return Response({
            'valid': True,
            'discountAmount': float(discount),
            'message': 'Voucher is valid'
        })

