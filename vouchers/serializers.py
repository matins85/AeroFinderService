from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Voucher, VoucherUser, VoucherUsage

User = get_user_model()


class VoucherUserSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='user.id', read_only=True)
    name = serializers.CharField(source='user.full_name', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = VoucherUser
        fields = ['id', 'name', 'email', 'created_at']


class VoucherSerializer(serializers.ModelSerializer):
    voucherId = serializers.CharField(source='voucher_id', read_only=True)
    minPurchase = serializers.DecimalField(source='min_purchase', max_digits=12, decimal_places=2, allow_null=True)
    maxDiscount = serializers.DecimalField(source='max_discount', max_digits=12, decimal_places=2, allow_null=True)
    usageLimit = serializers.IntegerField(source='usage_limit')
    usedCount = serializers.IntegerField(source='used_count')
    startDate = serializers.DateField(source='start_date')
    endDate = serializers.DateField(source='end_date')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    createdBy = serializers.CharField(source='created_by.email', read_only=True)
    targetUsers = serializers.CharField(source='target_users')
    users = VoucherUserSerializer(source='voucher_users', many=True, read_only=True)
    selectedUsers = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Voucher
        fields = [
            'voucherId', 'code', 'type', 'value', 'minPurchase', 'maxDiscount',
            'usageLimit', 'usedCount', 'status', 'startDate', 'endDate',
            'createdAt', 'description', 'createdBy', 'targetUsers', 'users', 'selectedUsers'
        ]
        read_only_fields = ['voucherId', 'usedCount', 'createdAt', 'createdBy']
    
    def create(self, validated_data):
        selected_users = validated_data.pop('selectedUsers', [])
        created_by = self.context['request'].user
        
        voucher = Voucher.objects.create(
            created_by=created_by,
            **validated_data
        )
        
        # Create VoucherUser entries if target is specific
        if voucher.target_users == 'specific' and selected_users:
            for user_id in selected_users:
                try:
                    user = User.objects.get(id=user_id)
                    VoucherUser.objects.create(voucher=voucher, user=user)
                except User.DoesNotExist:
                    pass
        
        return voucher


class VoucherValidateSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    discountAmount = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    message = serializers.CharField()

