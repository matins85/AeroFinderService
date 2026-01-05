import random
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from allauth.account.models import EmailConfirmation, EmailConfirmationHMAC, EmailAddress
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework.exceptions import APIException
from .models import CustomUser
from .serializers import (
    UserSerializer,
    SubAgentCreateSerializer, SubAgentUpdateSerializer,
    MultipleSubAgentCreateSerializer,
    MasterAgentCreationSerializer,
    AeroFinderPasswordResetSerializer,
    AeroFinderPasswordResetConfirmSerializer,
    ChangePasswordSerializer,
    ProfileUpdateSerializer,
    StaffCreationSerializer,
    ResendEmailSerializer,
)
from dj_rest_auth.registration.serializers import VerifyEmailSerializer
from .permissions import IsMasterAgentOrReadOnly
from audit.models import AuditLog
from dj_rest_auth.views import LoginView as RestAuthLoginView

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for user management"""
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]  # Allow authenticated users (admin and agents)
    
    def get_permissions(self):
        """Override permissions based on action"""
        if self.action in ['list', 'retrieve', 'activate', 'deactivate', 'sub_agents']:
            # Allow authenticated users (admin and agents) to list, view, activate/deactivate
            return [IsAuthenticated()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Only admins can create, update, delete users
            return [IsAdminUser()]
        return super().get_permissions()

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active']
    search_fields = ['email', 'first_name', 'last_name', 'phone_number']
    ordering_fields = ['date_joined', 'email']
    
    def get_queryset(self):
        queryset = CustomUser.objects.all()
        user = self.request.user
        
        # Agents can only see themselves and their sub-agents (if master agent)
        if user.is_authenticated and user.role == 'agent':
            if user.is_master_agent:
                # Master agents can see themselves and their sub-agents
                queryset = queryset.filter(Q(id=user.id) | Q(master_agent=user))
            else:
                # Regular agents can only see themselves
                queryset = queryset.filter(id=user.id)
        # Admins can see all users
        
        user_type = self.request.query_params.get('type')
        user_status = self.request.query_params.get('status')
        
        if user_type:
            if user_type == 'staff':
                queryset = queryset.filter(role='staff')
            elif user_type == 'agent':
                queryset = queryset.filter(role='agent')
            elif user_type == 'customer':
                queryset = queryset.filter(role='agent', is_master_agent=False)
        
        if user_status:
            queryset = queryset.filter(is_active=(user_status == 'active'))
        
        return queryset.select_related('agency', 'master_agent')
    
    @action(detail=True, methods=['get'], url_path='sub-agents')
    def sub_agents(self, request, pk=None):
        """Get sub-agents for a master agent"""
        user = self.get_object()
        if not user.is_master_agent:
            return Response(
                {'error': 'User is not a master agent'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        sub_agents = user.sub_agents.all()
        serializer = UserSerializer(sub_agents, many=True)
        return Response({'subAgents': serializer.data})
    
    @action(detail=True, methods=['post'], url_path='sub-agents', permission_classes=[IsMasterAgentOrReadOnly])
    def create_sub_agent(self, request, pk=None):
        """Create one or multiple sub-agents for master agent"""
        master_agent = self.get_object()
        if not master_agent.is_master_agent:
            return Response(
                {'error': 'User is not a master agent'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if request contains a list of sub-agents or a single sub-agent
        if 'subAgents' in request.data and isinstance(request.data['subAgents'], list):
            # Handle multiple sub-agents
            serializer = MultipleSubAgentCreateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            sub_agents_data = serializer.validated_data['subAgents']
            failed_agents = []
            
            # Check for duplicate emails in request and existing emails in database
            emails_in_request = [agent_data['email'] for agent_data in sub_agents_data]
            existing_emails = set(
                CustomUser.objects.filter(email__in=emails_in_request).values_list('email', flat=True)
            )
            
            # Check for duplicates in request
            seen_emails = set()
            duplicate_emails = set()
            for email in emails_in_request:
                if email in seen_emails:
                    duplicate_emails.add(email)
                seen_emails.add(email)
            
            # Filter out agents with duplicate/existing emails
            valid_agents_data = []
            email_password_map = {}  # Store email -> password mapping for email sending
            
            for sub_agent_data in sub_agents_data:
                email = sub_agent_data['email']
                if email in existing_emails:
                    failed_agents.append({
                        'email': email,
                        'error': 'Email already exists'
                    })
                    continue
                if email in duplicate_emails:
                    failed_agents.append({
                        'email': email,
                        'error': 'Duplicate email in request'
                    })
                    continue
                
                # Generate temporary password
                temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
                email_password_map[email] = temp_password
                valid_agents_data.append((sub_agent_data, temp_password))
            
            if not valid_agents_data:
                return Response(
                    {
                        'created': [],
                        'failed': failed_agents,
                        'total_requested': len(sub_agents_data),
                        'total_created': 0,
                        'total_failed': len(failed_agents)
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Bulk create sub-agents
            try:
                with transaction.atomic():
                    sub_agents_to_create = []
                    for sub_agent_data, temp_password in valid_agents_data:
                        user = CustomUser(
                            email=sub_agent_data['email'],
                            username=sub_agent_data['email'],
                            first_name=sub_agent_data['firstName'],
                            last_name=sub_agent_data['lastName'],
                            phone_number=sub_agent_data['phoneNumber'],
                            role='agent',
                            master_agent=master_agent,
                            is_active=True
                        )
                        user.set_password(temp_password)
                        sub_agents_to_create.append(user)
                    
                    # Bulk create sub-agents
                    created_sub_agents = CustomUser.objects.bulk_create(sub_agents_to_create)
                    
                    # Ensure IDs are available (bulk_create in Django 3.2+ should set IDs, but refetch if needed)
                    if created_sub_agents and not created_sub_agents[0].pk:
                        # IDs not set, refetch from database using emails
                        created_emails = [agent.email for agent in created_sub_agents]
                        created_sub_agents = list(CustomUser.objects.filter(email__in=created_emails))
                    
                    # Bulk create audit logs
                    ip_address = self._get_client_ip(request)
                    user_agent = request.META.get('HTTP_USER_AGENT', '')
                    audit_logs = [
                        AuditLog(
                            user=request.user,
                            action='CREATE_SUB_AGENT',
                            resource_type='User',
                            resource_id=str(sub_agent.id),
                            description=f'Created sub-agent {sub_agent.email}',
                            ip_address=ip_address,
                            user_agent=user_agent
                        )
                        for sub_agent in created_sub_agents
                    ]
                    AuditLog.objects.bulk_create(audit_logs)
                    
                    # Send email confirmations in parallel using ThreadPoolExecutor (like registration)
                    self._send_sub_agent_confirmation_emails_bulk(created_sub_agents, email_password_map, request)
                    
                    # Serialize created agents
                    created_agents = [UserSerializer(agent).data for agent in created_sub_agents]
                    
                    response_data = {
                        'created': created_agents,
                        'failed': failed_agents,
                        'total_requested': len(sub_agents_data),
                        'total_created': len(created_sub_agents),
                        'total_failed': len(failed_agents)
                    }
                    
                    return Response(
                        response_data,
                        status=status.HTTP_201_CREATED
                    )
            except Exception as e:
                # Rollback will happen automatically due to transaction.atomic()
                for sub_agent_data, _ in valid_agents_data:
                    failed_agents.append({
                        'email': sub_agent_data.get('email', 'unknown'),
                        'error': str(e)
                    })
                return Response(
                    {
                        'created': [],
                        'failed': failed_agents,
                        'total_requested': len(sub_agents_data),
                        'total_created': 0,
                        'total_failed': len(failed_agents),
                        'error': f'Failed to create sub-agents: {str(e)}'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # Handle single sub-agent (backward compatibility)
            serializer = SubAgentCreateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate temporary password
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            
            # Check if email already exists
            if CustomUser.objects.filter(email=serializer.validated_data['email']).exists():
                return Response(
                    {'error': 'Email already exists'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            sub_agent = CustomUser.objects.create_user(
                email=serializer.validated_data['email'],
                username=serializer.validated_data['email'],
                first_name=serializer.validated_data['firstName'],
                last_name=serializer.validated_data['lastName'],
                phone_number=serializer.validated_data['phoneNumber'],
                role='agent',
                master_agent=master_agent,
                password=temp_password
            )
            
            # Create EmailAddress and send confirmation email (like registration)
            from allauth.account.models import EmailAddress
            from allauth.account.utils import send_email_confirmation
            email_address, created = EmailAddress.objects.get_or_create(
                user=sub_agent,
                email=sub_agent.email,
                defaults={'primary': True, 'verified': False}
            )
            if created or not email_address.verified:
                try:
                    send_email_confirmation(request, sub_agent)
                except Exception as e:
                    # Log error but don't fail if email can't be sent
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to send confirmation email to {sub_agent.email}: {str(e)}")
            
            # Also send email with password
            self._send_sub_agent_credentials(
                sub_agent=sub_agent,
                password=temp_password,
                master_agent=master_agent
            )
            
            # Create audit log
            AuditLog.objects.create(
                user=request.user,
                action='CREATE_SUB_AGENT',
                resource_type='User',
                resource_id=str(sub_agent.id),
                description=f'Created sub-agent {sub_agent.email}',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response(UserSerializer(sub_agent).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['patch'], url_path='sub-agents/(?P<sub_agent_id>[^/.]+)',
            permission_classes=[IsMasterAgentOrReadOnly])
    def update_sub_agent(self, request, pk=None, sub_agent_id=None):
        """Update sub-agent status"""
        master_agent = self.get_object()
        try:
            sub_agent = master_agent.sub_agents.get(id=sub_agent_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'Sub-agent not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = SubAgentUpdateSerializer(data=request.data)
        if serializer.is_valid():
            status_value = serializer.validated_data['status']
            sub_agent.is_active = (status_value == 'active')
            sub_agent.save()
            
            # Create audit log
            AuditLog.objects.create(
                user=request.user,
                action='UPDATE_SUB_AGENT',
                resource_type='User',
                resource_id=str(sub_agent.id),
                description=f'Updated sub-agent {sub_agent.email} status to {status_value}',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response(UserSerializer(sub_agent).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['delete'], url_path='sub-agents/(?P<sub_agent_id>[^/.]+)',
            permission_classes=[IsMasterAgentOrReadOnly])
    def delete_sub_agent(self, request, pk=None, sub_agent_id=None):
        """Delete sub-agent"""
        master_agent = self.get_object()
        try:
            sub_agent = master_agent.sub_agents.get(id=sub_agent_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'Sub-agent not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create audit log
        AuditLog.objects.create(
            user=request.user,
            action='DELETE_SUB_AGENT',
            resource_type='User',
            resource_id=str(sub_agent.id),
            description=f'Deleted sub-agent {sub_agent.email}',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        sub_agent.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        """Activate a user (admin or agent can activate)"""
        user = self.get_object()
        
        # Check permissions: Admin can activate anyone, Agent can only activate their sub-agents
        if request.user.role == 'agent' and not request.user.is_master_agent:
            return Response(
                {'error': 'You do not have permission to activate users'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if request.user.role == 'agent' and request.user.is_master_agent:
            # Master agent can only activate their sub-agents
            if user.master_agent != request.user:
                return Response(
                    {'error': 'You can only activate your own sub-agents'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        if user.is_active:
            return Response(
                {'message': 'User is already active', 'user': UserSerializer(user).data},
                status=status.HTTP_200_OK
            )
        
        user.is_active = True
        user.save()
        
        # Create audit log
        AuditLog.objects.create(
            user=request.user,
            action='ACTIVATE_USER',
            resource_type='User',
            resource_id=str(user.id),
            description=f'Activated user {user.email}',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response(
            {'message': 'User activated successfully', 'user': UserSerializer(user).data},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        """Deactivate a user (admin or agent can deactivate)"""
        user = self.get_object()
        
        # Prevent deactivating yourself
        if user.id == request.user.id:
            return Response(
                {'error': 'You cannot deactivate yourself'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check permissions: Admin can deactivate anyone, Agent can only deactivate their sub-agents
        if request.user.role == 'agent' and not request.user.is_master_agent:
            return Response(
                {'error': 'You do not have permission to deactivate users'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if request.user.role == 'agent' and request.user.is_master_agent:
            # Master agent can only deactivate their sub-agents
            if user.master_agent != request.user:
                return Response(
                    {'error': 'You can only deactivate your own sub-agents'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        if not user.is_active:
            return Response(
                {'message': 'User is already inactive', 'user': UserSerializer(user).data},
                status=status.HTTP_200_OK
            )
        
        user.is_active = False
        user.save()
        
        # Create audit log
        AuditLog.objects.create(
            user=request.user,
            action='DEACTIVATE_USER',
            resource_type='User',
            resource_id=str(user.id),
            description=f'Deactivated user {user.email}',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response(
            {'message': 'User deactivated successfully', 'user': UserSerializer(user).data},
            status=status.HTTP_200_OK
        )
    
    @staticmethod
    def _get_client_ip(request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def _send_sub_agent_credentials(sub_agent, password, master_agent):
        """Send email with login credentials to sub-agent (single)"""
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        
        frontend_url = getattr(settings, 'URL_FRONT', 'http://localhost:3000')
        login_url = f"{frontend_url}/auth/login"
        master_agent_name = master_agent.get_full_name() or master_agent.email
        
        # Email subject
        subject = f'Your Sub-Agent Account Credentials - {master_agent_name}'
        
        # Context for template
        context = {
            'sub_agent_first_name': sub_agent.first_name,
            'sub_agent_last_name': sub_agent.last_name,
            'sub_agent_email': sub_agent.email,
            'password': password,
            'master_agent_name': master_agent_name,
            'login_url': login_url,
        }
        
        # Render HTML template
        html_message = render_to_string('account/email/sub_agent_credentials.html', context)
        plain_message = strip_tags(html_message)
        
        # Try to send email
        try:
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@aerofinder.com')
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_message,
                from_email=from_email,
                to=[sub_agent.email],
            )
            email.attach_alternative(html_message, "text/html")
            email.send()
        except Exception as e:
            # Log error but don't fail the creation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send credentials email to {sub_agent.email}: {str(e)}")
    
    @staticmethod
    def _send_sub_agent_confirmation_emails_bulk(sub_agents, email_password_map, request):
        """Send confirmation emails to multiple sub-agents in parallel using ThreadPoolExecutor"""
        from allauth.account.models import EmailAddress
        from allauth.account.utils import send_email_confirmation
        
        def send_confirmation_and_credentials(sub_agent):
            """Helper function to send confirmation email and credentials"""
            password = email_password_map.get(sub_agent.email)
            
            # Create EmailAddress and send confirmation email (like registration)
            email_address, created = EmailAddress.objects.get_or_create(
                user=sub_agent,
                email=sub_agent.email,
                defaults={'primary': True, 'verified': False}
            )
            if created or not email_address.verified:
                try:
                    send_email_confirmation(request, sub_agent)
                except Exception as e:
                    # Log error but don't fail if email can't be sent
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to send confirmation email to {sub_agent.email}: {str(e)}")
            
            # Also send credentials email with password
            # Find master agent from sub_agent
            master_agent = sub_agent.master_agent
            if master_agent and password:
                UserViewSet._send_sub_agent_credentials(sub_agent, password, master_agent)
            
            return sub_agent.email
        
        # Use ThreadPoolExecutor to send emails in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all email tasks
            future_to_email = {
                executor.submit(send_confirmation_and_credentials, sub_agent): sub_agent.email 
                for sub_agent in sub_agents
            }
            
            # Wait for all emails to be sent (or fail)
            for future in as_completed(future_to_email):
                email = future_to_email[future]
                try:
                    future.result()  # This will raise exception if email sending failed
                except Exception as e:
                    # Log error but continue with other emails
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to send confirmation email to {email}: {str(e)}")


class MasterAgentCreationView(APIView):
    """View for creating a master agent"""
    permission_classes = []  # Only admins can create master agents
    serializer_class = MasterAgentCreationSerializer
    
    def post(self, request):
        serializer = MasterAgentCreationSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.save(request)
            return Response(
                UserSerializer(user).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetView(APIView):
    """View for requesting password reset"""
    permission_classes = []  # Allow unauthenticated users
    
    def post(self, request):
        serializer = AeroFinderPasswordResetSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(
                {'message': 'Password reset e-mail has been sent.'},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(APIView):
    """View for confirming password reset"""
    permission_classes = []  # Allow unauthenticated users
    
    def post(self, request):
        serializer = AeroFinderPasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {'message': 'Password has been reset with the new password.'},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(RestAuthLoginView):
    """Login Endpoint"""
    
    def get_response(self):
        response = super().get_response()
        data = {
            "message": "Welcome {}".format(self.user),
            "code": response.status_code,
            "role": self.user.role,
            "user_id": self.user.id
        }
        response.data.update(data)
        return response


class ResendEmailConfirmationView(APIView):
    """ Resend E-mail Confirmation Endpoint """
    permission_classes = [AllowAny]
    serializer_class = ResendEmailSerializer

    def post(self, request):

        try:

            from allauth.account.models import EmailAddress
            from allauth.account.utils import send_email_confirmation

            user = User.objects.get(email=request.data['email'])
            email_address = EmailAddress.objects.filter(user=user, verified=True).exists()
            if email_address:
                return Response({'message': 'This email is already verified'},
                                status=status.HTTP_400_BAD_REQUEST)
            else:
                send_email_confirmation(request, user=user)
                return Response({'message': 'Verification email resent'},
                                status=status.HTTP_201_CREATED)
        except APIException:
            return Response({'message': 'This email does not exist, please create a new account'},
                            status=status.HTTP_403_FORBIDDEN)


class VerifyEmailView(APIView):
    """ Verify/Confirm E-mail Endpoint  """

    permission_classes = (AllowAny,)
    allowed_methods = ('POST', 'OPTIONS', 'HEAD')

    def get_serializer(self, *args, **kwargs):
        return VerifyEmailSerializer(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.kwargs['key'] = serializer.validated_data['key']
        try:
            confirmation = self.get_object()
            confirmation.confirm(self.request)
            return Response({'detail': _('Successfully confirmed email.')},
                            status=status.HTTP_200_OK)
        except EmailConfirmation.DoesNotExist:
            return Response({'detail': _('Invalid Token.')},
                            status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # Handle ImmediateHttpResponse from allauth signals
            from allauth.exceptions import ImmediateHttpResponse
            if isinstance(e, ImmediateHttpResponse):
                # Extract the response from the exception and return it
                # Convert JsonResponse to DRF Response
                import json
                from rest_framework.response import Response as DRFResponse
                json_response = e.response
                response_data = json.loads(json_response.content.decode('utf-8'))
                return DRFResponse(response_data, status=json_response.status_code)
            # Handle any other exceptions
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error during email confirmation: {str(e)}")
            return Response(
                {'detail': _('An error occurred during email confirmation.')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_object(self, queryset=None):
        key = self.kwargs['key']
        email_confirmation = EmailConfirmationHMAC.from_key(key)
        if not email_confirmation:
            if queryset is None:
                queryset = self.get_queryset()
            try:
                email_confirmation = queryset.get(key=key.lower())
            except EmailConfirmation.DoesNotExist:
                raise EmailConfirmation.DoesNotExist
        return email_confirmation

    def get_queryset(self):
        qs = EmailConfirmation.objects.all_valid()
        qs = qs.select_related("email_address__user")
        return qs


class ChangePasswordView(APIView):
    """View for changing password"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(
                {'message': 'Password has been changed successfully.'},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfileUpdateView(APIView):
    """View for updating user profile"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request):
        """Update user profile"""
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                UserSerializer(user).data,
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request):
        """Partial update user profile"""
        return self.put(request)


class StaffCreationView(APIView):
    """View for creating staff members"""
    permission_classes = [IsAdminUser]  # Only admins can create staff
    
    def post(self, request):
        serializer = StaffCreationSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.save(request)
            return Response(
                UserSerializer(user).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserStatsView(APIView):
    """View for user statistics with filters"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get user statistics with optional filters"""
        # Get filter parameters
        role_filter = request.query_params.get('role')  # staff, agent, admin
        status_filter = request.query_params.get('status')  # active, inactive
        
        # Base queryset - apply filters
        queryset = CustomUser.objects.all()
        
        # Apply role filter
        if role_filter and role_filter in ['staff', 'agent', 'admin']:
            queryset = queryset.filter(role=role_filter)
        
        # Apply status filter
        if status_filter:
            if status_filter == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter == 'inactive':
                queryset = queryset.filter(is_active=False)
        
        # Calculate statistics based on filtered queryset
        # If role filter is applied, only show counts for that role
        if role_filter == 'staff':
            stats = {
                'totalStaff': queryset.count(),
                'totalAgents': 0,
                'totalCustomers': 0,
                'activeUsers': queryset.filter(is_active=True).count(),
                'inactiveUsers': queryset.filter(is_active=False).count(),
                'totalUsers': queryset.count(),
            }
        elif role_filter == 'agent':
            stats = {
                'totalStaff': 0,
                'totalAgents': queryset.count(),
                'totalCustomers': queryset.filter(is_master_agent=False).count(),
                'activeUsers': queryset.filter(is_active=True).count(),
                'inactiveUsers': queryset.filter(is_active=False).count(),
                'totalUsers': queryset.count(),
                'totalMasterAgents': queryset.filter(is_master_agent=True).count(),
            }
        elif role_filter == 'admin':
            stats = {
                'totalStaff': 0,
                'totalAgents': 0,
                'totalCustomers': 0,
                'activeUsers': queryset.filter(is_active=True).count(),
                'inactiveUsers': queryset.filter(is_active=False).count(),
                'totalUsers': queryset.count(),
                'totalAdmins': queryset.count(),
            }
        else:
            # No role filter - show all statistics
            stats = {
                'totalStaff': CustomUser.objects.filter(role='staff').count(),
                'totalAgents': CustomUser.objects.filter(role='agent').count(),
                'totalCustomers': CustomUser.objects.filter(role='agent', is_master_agent=False).count(),
                'activeUsers': queryset.filter(is_active=True).count() if status_filter else CustomUser.objects.filter(is_active=True).count(),
                'inactiveUsers': queryset.filter(is_active=False).count() if status_filter else CustomUser.objects.filter(is_active=False).count(),
                'totalUsers': queryset.count(),
                'totalAdmins': CustomUser.objects.filter(role='admin').count(),
                'totalMasterAgents': CustomUser.objects.filter(role='agent', is_master_agent=True).count(),
            }
        
        # Add filters applied
        stats['filters'] = {
            'role': role_filter or 'all',
            'status': status_filter or 'all'
        }
        
        return Response(stats, status=status.HTTP_200_OK)


