from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode as uid_decoder
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from dj_rest_auth.registration.serializers import RegisterSerializer
from .models import CustomUser, Agency
from .forms import PasswordResetForm

User = get_user_model()


class AgencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Agency
        fields = ['agency_name', 'agency_email', 'agency_address', 'agency_phone', 'created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    agency = AgencySerializer(read_only=True)
    agencyName = serializers.CharField(source='agency.agency_name', read_only=True)
    agencyEmail = serializers.CharField(source='agency.agency_email', read_only=True)
    agencyAddress = serializers.CharField(source='agency.agency_address', read_only=True)
    agencyPhone = serializers.CharField(source='agency.agency_phone', read_only=True)
    masterAgentId = serializers.CharField(source='master_agent.id', read_only=True, allow_null=True)
    firstName = serializers.CharField(source='first_name')
    lastName = serializers.CharField(source='last_name')
    phoneNumber = serializers.CharField(source='phone_number')
    isMasterAgent = serializers.BooleanField(source='is_master_agent')
    createdAt = serializers.DateTimeField(source='date_joined', read_only=True)
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'firstName', 'lastName', 'phoneNumber', 'role',
            'agency', 'agencyName', 'agencyEmail', 'agencyAddress', 'agencyPhone',
            'isMasterAgent', 'masterAgentId', 'is_active', 'createdAt'
        ]
        read_only_fields = ['id', 'createdAt', 'agency']


class CustomRegisterSerializer(RegisterSerializer):
    """Custom registration serializer for dj-rest-auth with agency details"""
    firstName = serializers.CharField(required=True)
    lastName = serializers.CharField(required=True)
    phoneNumber = serializers.CharField(required=True)
    agencyName = serializers.CharField(required=True)
    agencyEmail = serializers.EmailField(required=True)
    agencyAddress = serializers.CharField(required=True)
    agencyPhone = serializers.CharField(required=True)
    isMasterAgent = serializers.BooleanField(default=False, required=False)
    subAgents = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True
    )
    
    def get_cleaned_data(self):
        return {
            'username': self.validated_data.get('username', ''),
            'password1': self.validated_data.get('password1', ''),
            'email': self.validated_data.get('email', ''),
            'firstName': self.validated_data.get('firstName', ''),
            'lastName': self.validated_data.get('lastName', ''),
            'phoneNumber': self.validated_data.get('phoneNumber', ''),
            'isMasterAgent': self.validated_data.get('isMasterAgent', False),
        }
    
    def save(self, request):
        from allauth.account import app_settings as allauth_settings
        from allauth.utils import email_address_exists
        
        cleaned_data = self.get_cleaned_data()
        email = cleaned_data.get('email')
        
        if allauth_settings.UNIQUE_EMAIL:
            if email and email_address_exists(email):
                raise serializers.ValidationError({
                    'email': 'A user is already registered with this email address.'
                })
        
        # Create user
        user = CustomUser.objects.create_user(
            username=cleaned_data.get('username') or email,
            email=email,
            password=cleaned_data.get('password1'),
            first_name=cleaned_data.get('firstName'),
            last_name=cleaned_data.get('lastName'),
            phone_number=cleaned_data.get('phoneNumber'),
            is_master_agent=cleaned_data.get('isMasterAgent', False),
            role='agent'
        )
        
        # Create agency
        Agency.objects.create(
            user=user,
            agency_name=self.validated_data.get('agencyName'),
            agency_email=self.validated_data.get('agencyEmail'),
            agency_address=self.validated_data.get('agencyAddress'),
            agency_phone=self.validated_data.get('agencyPhone')
        )
        
        # Create sub-agents if master agent
        sub_agents_data = self.validated_data.get('subAgents', [])
        if user.is_master_agent and sub_agents_data:
            for sub_agent_data in sub_agents_data:
                CustomUser.objects.create_user(
                    email=sub_agent_data.get('email'),
                    username=sub_agent_data.get('email'),
                    first_name=sub_agent_data.get('firstName', ''),
                    last_name=sub_agent_data.get('lastName', ''),
                    phone_number=sub_agent_data.get('phoneNumber', ''),
                    role='agent',
                    master_agent=user,
                    password=sub_agent_data.get('password', 'temp123456')
                )
        
        return user


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Legacy serializer - kept for backward compatibility, but use CustomRegisterSerializer with dj-rest-auth"""
    firstName = serializers.CharField(source='first_name', write_only=True)
    lastName = serializers.CharField(source='last_name', write_only=True)
    phoneNumber = serializers.CharField(source='phone_number', write_only=True)
    agencyName = serializers.CharField(write_only=True)
    agencyEmail = serializers.EmailField(write_only=True)
    agencyAddress = serializers.CharField(write_only=True)
    agencyPhone = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, min_length=6)
    confirmPassword = serializers.CharField(write_only=True)
    isMasterAgent = serializers.BooleanField(source='is_master_agent', default=False, write_only=True)
    subAgents = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True
    )
    
    class Meta:
        model = CustomUser
        fields = [
            'email', 'firstName', 'lastName', 'phoneNumber', 'password',
            'confirmPassword', 'agencyName', 'agencyEmail', 'agencyAddress',
            'agencyPhone', 'isMasterAgent', 'subAgents'
        ]
    
    def validate(self, attrs):
        if attrs['password'] != attrs['confirmPassword']:
            raise serializers.ValidationError({'password': 'Passwords do not match'})
        return attrs
    
    def create(self, validated_data):
        # Extract agency data and sub-agents
        agency_name = validated_data.pop('agencyName')
        agency_email = validated_data.pop('agencyEmail')
        agency_address = validated_data.pop('agencyAddress')
        agency_phone = validated_data.pop('agencyPhone')
        sub_agents_data = validated_data.pop('subAgents', [])
        validated_data.pop('confirmPassword')
        
        # Create user
        password = validated_data.pop('password')
        username = validated_data.get('email')  # Use email as username
        validated_data['username'] = username
        
        user = CustomUser.objects.create_user(
            password=password,
            **validated_data
        )
        
        # Create agency
        Agency.objects.create(
            user=user,
            agency_name=agency_name,
            agency_email=agency_email,
            agency_address=agency_address,
            agency_phone=agency_phone
        )
        
        # Create sub-agents if master agent
        if user.is_master_agent and sub_agents_data:
            for sub_agent_data in sub_agents_data:
                CustomUser.objects.create_user(
                    email=sub_agent_data['email'],
                    username=sub_agent_data['email'],
                    first_name=sub_agent_data['firstName'],
                    last_name=sub_agent_data['lastName'],
                    phone_number=sub_agent_data['phoneNumber'],
                    role='agent',
                    master_agent=user,
                    password=sub_agent_data.get('password', 'temp123456')  # Should generate temp password
                )
        
        return user


class SubAgentCreateSerializer(serializers.Serializer):
    firstName = serializers.CharField()
    lastName = serializers.CharField()
    email = serializers.EmailField()
    phoneNumber = serializers.CharField()


class MultipleSubAgentCreateSerializer(serializers.Serializer):
    """Serializer for creating multiple sub-agents at once"""
    subAgents = serializers.ListField(
        child=SubAgentCreateSerializer(),
        min_length=1,
        help_text="List of sub-agents to create"
    )


class SubAgentUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['active', 'inactive'])


class MasterAgentCreationSerializer(serializers.Serializer):
    """Serializer for creating a master agent with password from user"""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, min_length=6)
    firstName = serializers.CharField(required=True)
    lastName = serializers.CharField(required=True)
    phoneNumber = serializers.CharField(required=True)
    agencyName = serializers.CharField(required=True)
    agencyEmail = serializers.EmailField(required=True)
    agencyAddress = serializers.CharField(required=True)
    agencyPhone = serializers.CharField(required=True)
    
    def validate_email(self, email):
        if CustomUser.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email
    
    def save(self, request):
        """Create master agent and agency"""
        from allauth.account.models import EmailAddress
        from allauth.account.utils import send_email_confirmation
        
        # Create user directly with password from user
        user = CustomUser.objects.create_user(
            email=self.validated_data['email'],
            username=self.validated_data['email'],
            password=self.validated_data['password'],  # Password passed by user
            first_name=self.validated_data['firstName'],
            last_name=self.validated_data['lastName'],
            phone_number=self.validated_data['phoneNumber'],
            role='agent',
            is_master_agent=True
        )
        
        # Create agency
        Agency.objects.create(
            user=user,
            agency_name=self.validated_data['agencyName'],
            agency_email=self.validated_data['agencyEmail'],
            agency_address=self.validated_data['agencyAddress'],
            agency_phone=self.validated_data['agencyPhone']
        )
        
        # Create EmailAddress and send confirmation email (like registration)
        email_address, created = EmailAddress.objects.get_or_create(
            user=user,
            email=user.email,
            defaults={'primary': True, 'verified': False}
        )
        if created or not email_address.verified:
            try:
                send_email_confirmation(request, user)
            except Exception as e:
                # Log error but don't fail user creation if email can't be sent
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send confirmation email to {user.email}: {str(e)}")
        
        return user


class AeroFinderPasswordResetSerializer(serializers.Serializer):
    """
    Serializer for requesting a password reset e-mail.
    """
    email = serializers.EmailField()

    def validate_email(self, email):
        # Create PasswordResetForm with the serializer
        if not User.objects.filter(email=email).exists():
            raise serializers.ValidationError(_('Invalid e-mail address'))

        self.reset_form = PasswordResetForm(email)
        return email

    def save(self):
        request = self.context.get('request')
        # Set some values to trigger the send_email method.
        opts = {
            'use_https': request.is_secure(),
            'from_email': getattr(settings, 'DEFAULT_FROM_EMAIL'),
            'request': request,
        }
        self.reset_form.save(**opts)


class AeroFinderPasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset with token.
    """
    new_password1 = serializers.CharField(max_length=128)
    new_password2 = serializers.CharField(max_length=128)
    uid = serializers.CharField()
    token = serializers.CharField()

    set_password_form_class = SetPasswordForm

    def custom_validation(self, attrs):
        """Override this method to add custom validation logic"""
        pass

    def validate(self, attrs):
        self._errors = {}

        # Decode the uidb64 to uid to get User object
        try:
            uid = force_str(uid_decoder(attrs['uid']))
            self.user = User._default_manager.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({'uid': ['Invalid Token']})

        self.custom_validation(attrs)
        # Construct SetPasswordForm instance
        self.set_password_form = self.set_password_form_class(
            user=self.user, data=attrs
        )
        if not self.set_password_form.is_valid():
            raise serializers.ValidationError(self.set_password_form.errors)
        if not default_token_generator.check_token(self.user, attrs['token']):
            raise serializers.ValidationError({'token': ['Invalid Token']})

        return attrs

    def save(self):
        return self.set_password_form.save()


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing password.
    """
    old_password = serializers.CharField(required=True, write_only=True)
    new_password1 = serializers.CharField(required=True, write_only=True, min_length=6)
    new_password2 = serializers.CharField(required=True, write_only=True, min_length=6)
    
    def validate(self, attrs):
        if attrs['new_password1'] != attrs['new_password2']:
            raise serializers.ValidationError({
                'new_password2': _("The two password fields didn't match.")
            })
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_('Your old password was entered incorrectly.'))
        return value
    
    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password1'])
        user.save()
        return user


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile"""
    firstName = serializers.CharField(source='first_name', required=False)
    lastName = serializers.CharField(source='last_name', required=False)
    phoneNumber = serializers.CharField(source='phone_number', required=False)
    
    class Meta:
        model = CustomUser
        fields = ['firstName', 'lastName', 'phoneNumber']
    
    def update(self, instance, validated_data):
        # Update only provided fields
        if 'first_name' in validated_data:
            instance.first_name = validated_data['first_name']
        if 'last_name' in validated_data:
            instance.last_name = validated_data['last_name']
        if 'phone_number' in validated_data:
            instance.phone_number = validated_data['phone_number']
        instance.save()
        return instance


class StaffCreationSerializer(serializers.Serializer):
    """Serializer for creating staff members"""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, min_length=6)
    firstName = serializers.CharField(required=True)
    lastName = serializers.CharField(required=True)
    phoneNumber = serializers.CharField(required=True)
    
    def validate_email(self, email):
        if CustomUser.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email
    
    def save(self, request):
        """Create staff member and send confirmation email with password"""
        from allauth.account.models import EmailAddress
        from allauth.account.utils import send_email_confirmation
        
        # Create user with staff role
        user = CustomUser.objects.create_user(
            email=self.validated_data['email'],
            username=self.validated_data['email'],
            password=self.validated_data['password'],  # Password passed by admin
            first_name=self.validated_data['firstName'],
            last_name=self.validated_data['lastName'],
            phone_number=self.validated_data['phoneNumber'],
            role='staff'
        )
        
        # Create EmailAddress and send confirmation email (like registration)
        email_address, created = EmailAddress.objects.get_or_create(
            user=user,
            email=user.email,
            defaults={'primary': True, 'verified': False}
        )
        if created or not email_address.verified:
            try:
                send_email_confirmation(request, user)
            except Exception as e:
                # Log error but don't fail user creation if email can't be sent
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send confirmation email to {user.email}: {str(e)}")
        
        # Also send email with password (for staff creation)
        try:
            self._send_staff_credentials_email(request, user, self.validated_data['password'])
        except Exception as e:
            # Log error but don't fail user creation if email can't be sent
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send staff credentials email to {user.email}: {str(e)}")
        
        return user
    
    def _send_staff_credentials_email(self, request, user, password):
        """Send email with credentials to staff member"""
        from allauth.account.utils import send_email_confirmation
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        
        frontend_url = getattr(settings, 'URL_FRONT', getattr(settings, 'FRONT_END_URL', 'http://localhost:3000'))
        
        # Get email confirmation key for activation link
        from allauth.account.models import EmailAddress
        email_address = EmailAddress.objects.filter(user=user, primary=True).first()
        confirmation_key = None
        if email_address:
            from allauth.account.models import EmailConfirmation
            confirmation = EmailConfirmation.objects.filter(email_address=email_address).first()
            if confirmation:
                confirmation_key = confirmation.key
        
        activation_link = f"{frontend_url}/account-confirm-email/{confirmation_key}/" if confirmation_key else frontend_url
        
        template_context = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'password': password,
            'activation_link': activation_link,
            'website': frontend_url,
            'site_name': getattr(settings, 'SITE_NAME', 'AeroFinder'),
        }
        
        # Render HTML template for staff credentials
        html_message = render_to_string('account/email/staff_credentials.html', template_context)
        plain_message = strip_tags(html_message)
        
        subject = f'Welcome to {template_context["site_name"]} - Staff Account Created'
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@aerofinder.com')
        
        msg = EmailMultiAlternatives(subject, plain_message, from_email, [user.email])
        msg.attach_alternative(html_message, "text/html")
        msg.send()


class ResendEmailSerializer(serializers.Serializer):
    """ Serializer for resend email Endpoint """

    email = serializers.CharField()
