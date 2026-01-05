from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet, UserStatsView,
    MasterAgentCreationView,
    PasswordResetView,
    PasswordResetConfirmView,
    UserLoginView,
    ResendEmailConfirmationView,
    VerifyEmailView,
    ChangePasswordView,
    ProfileUpdateView,
    StaffCreationView
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('auth/', include('dj_rest_auth.urls')),  # Login, logout, password reset, etc.
    path('auth/registration/', include('dj_rest_auth.registration.urls')),  # Registration with custom serializer
    path('rest-auth/accounts/login/', UserLoginView.as_view(), name='custom-login'),
    path('rest-auth/resend-confirmation-email/', ResendEmailConfirmationView.as_view(), name='resend-email-confirmation'),
    path('account-confirm-email/', VerifyEmailView.as_view(), name='account_email_verification_sent'),
    path('account-confirm-email/<str:key>/', VerifyEmailView.as_view(), name='account_confirm_email'),
    path('auth/password-reset/', PasswordResetView.as_view(), name='password-reset'),
    path('auth/password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('auth/profile/', ProfileUpdateView.as_view(), name='profile-update'),
    path('auth/master-agent/', MasterAgentCreationView.as_view(), name='master-agent-creation'),
    path('auth/staff/', StaffCreationView.as_view(), name='staff-creation'),
    path('users/stats/', UserStatsView.as_view(), name='user-stats'),  # User statistics endpoint
    path('', include(router.urls)),
]
