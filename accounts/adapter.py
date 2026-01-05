from allauth.account.adapter import DefaultAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
from django.http import HttpResponseBadRequest
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

class DefaultAccountAdapterCustom(DefaultAccountAdapter):
    """Custom account adapter for handling registration with agency details"""

    def send_mail(self, template_prefix, email, context):
        """Send email with activation link"""
        context['activate_url'] = settings.URL_FRONT + '/auth/verify-email/' + context['key']
        context['first_name'] = context['user'].first_name
        msg = self.render_mail(template_prefix, email, context)
        msg.send()
    
    def save_user(self, request, user, form, commit=True):
        """Override save_user to handle custom fields from registration"""
        user = super().save_user(request, user, form, commit=False)
        
        # Save additional custom fields if they exist in form.cleaned_data
        if 'first_name' in form.cleaned_data:
            user.first_name = form.cleaned_data['first_name']
        if 'last_name' in form.cleaned_data:
            user.last_name = form.cleaned_data['last_name']
        if 'phone_number' in form.cleaned_data:
            user.phone_number = form.cleaned_data['phone_number']
        if 'role' in form.cleaned_data:
            user.role = form.cleaned_data['role']
        if 'is_master_agent' in form.cleaned_data:
            user.is_master_agent = form.cleaned_data['is_master_agent']
        
        if commit:
            user.save()
        
        return user
