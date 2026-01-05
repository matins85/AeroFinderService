from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
from .models import AuditLog
from accounts.permissions import IsStaff
from .serializers import AuditLogSerializer, AuditLogDetailSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing audit logs
    - Admins can see all logs
    - Regular users can only see their own logs
    """

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AuditLogDetailSerializer
        return AuditLogSerializer

    def get_queryset(self):
        user = self.request.user

        # Admins see all logs
        if user.is_staff:
            queryset = AuditLog.objects.all()
        else:
            # Regular users see only their own logs
            queryset = AuditLog.objects.filter(user=user)

        # Filter by action type
        action = self.request.query_params.get('action', None)
        if action:
            queryset = queryset.filter(action=action)

        # Filter by model name
        model_name = self.request.query_params.get('model_name', None)
        if model_name:
            queryset = queryset.filter(model_name__icontains=model_name)

        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)

        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)

        # Search by username (admin only)
        if user.is_staff:
            username = self.request.query_params.get('username', None)
            if username:
                queryset = queryset.filter(user__username__icontains=username)

        return queryset.select_related('user')

    def get_permissions(self):
        """
        Anyone authenticated can view their own logs
        Only admins can view all logs
        """
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsStaff()]

    @action(detail=False, methods=['get'])
    def my_logs(self, request):
        """
        Endpoint for users to view their own logs
        """
        logs = AuditLog.objects.filter(user=request.user)

        # Apply filters
        action = request.query_params.get('action', None)
        if action:
            logs = logs.filter(action=action)

        page = self.paginate_queryset(logs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsStaff])
    def stats(self, request):
        """
        Admin endpoint to get audit log statistics
        """

        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)

        stats = {
            'total_logs': AuditLog.objects.count(),
            'logs_last_24h': AuditLog.objects.filter(timestamp__gte=last_24h).count(),
            'logs_last_7d': AuditLog.objects.filter(timestamp__gte=last_7d).count(),
            'logs_last_30d': AuditLog.objects.filter(timestamp__gte=last_30d).count(),
            'logs_by_action': dict(
                AuditLog.objects.values('action').annotate(count=Count('id')).values_list('action', 'count')
            ),
            'logs_by_model': dict(
                AuditLog.objects.exclude(model_name__isnull=True).values('model_name').annotate(
                    count=Count('id')).values_list('model_name', 'count')[:10]
            ),
            'top_users': list(
                AuditLog.objects.values('user__username', 'user__email').annotate(count=Count('id')).order_by('-count')[
                    :10]
            ),
        }
        return Response(stats)
