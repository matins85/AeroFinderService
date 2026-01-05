import requests
import logging
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)


class PaystackService:
    """Service for handling Paystack payment integration"""
    
    def __init__(self):
        self.secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
        self.public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '')
        self.base_url = 'https://api.paystack.co'
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
    
    def initialize_transaction(self, email, amount, reference, callback_url=None, metadata=None):
        """
        Initialize a Paystack transaction
        Args:
            email: Customer email
            amount: Amount in kobo (for NGN) or smallest currency unit
            reference: Unique transaction reference
            callback_url: URL to redirect after payment
            metadata: Additional metadata
        Returns:
            dict: Response from Paystack API
        """
        url = f'{self.base_url}/transaction/initialize'
        
        # Convert amount to kobo (smallest NGN unit)
        amount_in_kobo = int(Decimal(str(amount)) * 100)
        
        payload = {
            'email': email,
            'amount': amount_in_kobo,
            'reference': reference,
            'currency': 'NGN',
            'metadata': metadata or {}
        }
        
        if callback_url:
            payload['callback_url'] = callback_url
        
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack initialization error: {e}")
            return {'status': False, 'message': str(e)}
    
    def verify_transaction(self, reference):
        """
        Verify a Paystack transaction
        Args:
            reference: Transaction reference
        Returns:
            dict: Transaction details from Paystack
        """
        url = f'{self.base_url}/transaction/verify/{reference}'
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack verification error: {e}")
            return {'status': False, 'message': str(e)}
    
    def verify_webhook(self, payload, signature):
        """
        Verify Paystack webhook signature
        Args:
            payload: Webhook payload (string)
            signature: X-Paystack-Signature header value
        Returns:
            bool: True if signature is valid
        """
        import hmac
        import hashlib
        
        computed_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, signature)
    
    def create_virtual_account(self, email, first_name, last_name, phone_number, reference=None):
        """
        Create a virtual account for a customer
        Args:
            email: Customer email
            first_name: Customer first name
            last_name: Customer last name
            phone_number: Customer phone number
            reference: Optional custom reference
        Returns:
            dict: Response from Paystack API
        """
        url = f'{self.base_url}/customer'
        
        # First, create or get customer
        customer_payload = {
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone_number,
        }
        
        try:
            # Try to create customer first
            customer_response = requests.post(url, json=customer_payload, headers=self.headers, timeout=30)
            
            if customer_response.status_code == 422:
                # Customer already exists, try to get them by email
                get_url = f'{self.base_url}/customer'
                params = {'email': email}
                customer_response = requests.get(get_url, params=params, headers=self.headers, timeout=30)
            
            customer_response.raise_for_status()
            customer_data = customer_response.json()
            
            if not customer_data.get('status'):
                return {'status': False, 'message': 'Failed to create/get customer', 'data': customer_data}
            
            # Handle both single customer and list response
            if isinstance(customer_data['data'], list):
                customer_code = customer_data['data'][0]['customer_code']
            else:
                customer_code = customer_data['data']['customer_code']
            
            # Now create virtual account
            va_url = f'{self.base_url}/dedicated_account'
            va_payload = {
                'customer': customer_code,
                'preferred_bank': 'wema-bank',  # Default bank, can be made configurable
            }
            
            if reference:
                va_payload['account_name'] = reference
            
            va_response = requests.post(va_url, json=va_payload, headers=self.headers, timeout=30)
            va_response.raise_for_status()
            va_data = va_response.json()
            
            return va_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack virtual account creation error: {e}")
            return {'status': False, 'message': str(e)}

