from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from .models import AuditLog

User = get_user_model()


class AuditLogModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_audit_log_creation(self):
        audit_log = AuditLog.objects.create(
            user=self.user,
            action='LOGIN',
            ip_address='127.0.0.1'
        )
        self.assertEqual(audit_log.user, self.user)
        self.assertEqual(audit_log.action, 'LOGIN')
        self.assertEqual(audit_log.ip_address, '127.0.0.1')

    def test_audit_log_string_representation(self):
        audit_log = AuditLog.objects.create(
            user=self.user,
            action='CREATE',
        )
        expected_str = f"{self.user} - CREATE - {audit_log.timestamp}"
        self.assertEqual(str(audit_log), expected_str)


class AuditLogAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='adminpass123',
            is_staff=True
        )

    def test_audit_log_list_authenticated(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('auditlog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_audit_log_list_unauthenticated(self):
        url = reverse('auditlog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_my_activity_endpoint(self):
        AuditLog.objects.create(
            user=self.user,
            action='LOGIN',
            ip_address='127.0.0.1'
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('auditlog-my-activity')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_stats_endpoint_admin_access(self):
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('auditlog-stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_logs', response.data)
        self.assertIn('action_counts', response.data)

    def test_stats_endpoint_regular_user_denied(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('auditlog-stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)