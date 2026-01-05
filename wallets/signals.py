from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from allauth.account.signals import email_confirmed
from accounts.models import CustomUser
from .models import Wallet
from .services import create_virtual_account_for_user
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CustomUser)
def create_user_wallet(sender, instance, created, **kwargs):
    """Create wallet when user is created (but don't create virtual account yet)"""
    if created:
        Wallet.objects.create(user=instance)


@receiver(email_confirmed)
def create_virtual_account_on_email_confirmation(request, email_address, **kwargs):
    """
    Create virtual account when user confirms their email
    If virtual account creation fails, prevent email confirmation
    """
    user = email_address.user
    
    # Only create virtual account if user doesn't have one yet
    wallet, _ = Wallet.objects.get_or_create(user=user)
    
    if wallet.virtual_account_created:
        logger.info(f"User {user.email} already has a virtual account")
        return
    
    # Create virtual account
    success, error_message, account_data = create_virtual_account_for_user(user)
    
    if success and account_data:
        # Update wallet with virtual account details
        wallet.virtual_account_number = account_data['virtual_account_number']
        wallet.virtual_account_bank = account_data['virtual_account_bank']
        wallet.virtual_account_name = account_data['virtual_account_name']
        wallet.virtual_account_reference = account_data['virtual_account_reference']
        wallet.virtual_account_created = True
        wallet.virtual_account_creation_error = None
        wallet.save()
        
        logger.info(f"Virtual account created successfully for user {user.email}")
    else:
        # Store error and prevent email confirmation
        wallet.virtual_account_creation_error = error_message
        wallet.save()
        
        # Unconfirm the email address
        email_address.verified = False
        email_address.save()
        
        logger.error(f"Failed to create virtual account for user {user.email}: {error_message}")
        
        # Raise exception to prevent email confirmation
        from allauth.exceptions import ImmediateHttpResponse
        from django.http import JsonResponse
        raise ImmediateHttpResponse(
            JsonResponse({
                'error': 'Account activation failed',
                'message': 'Failed to create virtual account. Please contact support.',
                'details': error_message
            }, status=400)
        )
