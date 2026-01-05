from django.conf import settings
from bookings.services import PaystackService


def create_virtual_account_for_user(user):
    """
    Create a virtual account for a user
    Args:
        user: CustomUser instance
    Returns:
        tuple: (success: bool, error_message: str, account_data: dict)
    """
    # Check if Paystack secret key is configured
    paystack_secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not paystack_secret_key:
        error_message = 'Paystack secret key is not configured. Please contact support.'
        print(f"Paystack secret key not configured. Cannot create virtual account for user {user.email}")
        return False, error_message, None
    
    try:
        paystack_service = PaystackService()
        
        # Generate reference
        reference = f"VA-{user.id}-{user.email.split('@')[0]}"
        
        # Create virtual account via Paystack
        response = paystack_service.create_virtual_account(
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone_number=user.phone_number,
            reference=reference
        )
        
        if not response.get('status'):
            error_message = response.get('message', 'Failed to create virtual account')
            # Check for authentication errors
            if '401' in error_message or 'Unauthorized' in error_message:
                error_message = 'Paystack authentication failed. Please check your API keys configuration.'
            print(f"Failed to create virtual account for user {user.email}: {error_message}")
            return False, error_message, None
        
        # Extract account details
        account_data = response.get('data', {})
        account_info = account_data.get('account', {})
        
        # Handle different response structures
        if isinstance(account_info, list) and len(account_info) > 0:
            account_info = account_info[0]
        
        # Extract bank name
        bank_info = account_info.get('bank', {})
        if isinstance(bank_info, dict):
            bank_name = bank_info.get('name', 'Wema Bank')
        else:
            bank_name = account_info.get('bankName', 'Wema Bank')
        
        virtual_account_data = {
            'virtual_account_number': account_info.get('account_number') or account_info.get('accountNumber'),
            'virtual_account_bank': bank_name,
            'virtual_account_name': account_info.get('account_name') or account_info.get('accountName', f"{user.first_name} {user.last_name}"),
            'virtual_account_reference': account_data.get('dedicated_account', {}).get('account_number') if isinstance(account_data.get('dedicated_account'), dict) else account_data.get('dedicated_account') or reference,
            'virtual_account_created': True,
            'virtual_account_creation_error': None
        }
        
        return True, None, virtual_account_data
        
    except Exception as e:
        error_message = f"Exception creating virtual account: {str(e)}"
        print(f"Exception creating virtual account for user {user.email}: {error_message}")
        return False, error_message, None

