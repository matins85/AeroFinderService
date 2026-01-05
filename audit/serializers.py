from rest_framework import serializers
from typing import Dict, Any
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    changes = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            'id',
            'user',
            'username',
            'user_email',
            'action',
            'model_name',
            'object_id',
            'object_repr',
            'before_data',
            'after_data',
            'changes',
            'description',
            'ip_address',
            'user_agent',
            'timestamp',
        ]
        read_only_fields = ['id', 'timestamp']

    def get_changes(self, obj) -> Dict[str, Any]:
        """
        Returns only the fields that changed with before/after values
        """
        return obj.get_changes()


class AuditLogDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for single audit log view
    """
    username = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    changes = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            'id',
            'user',
            'username',
            'user_email',
            'action',
            'model_name',
            'object_id',
            'object_repr',
            'before_data',
            'after_data',
            'changes',
            'description',
            'ip_address',
            'user_agent',
            'timestamp',
        ]

    def get_changes(self, obj) -> Dict[str, Any]:
        return obj.get_changes()
