from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode as uid_encoder
from django_rest_passwordreset.signals import reset_password_token_created
from django.contrib.sites.models import Site

current_site = Site.objects.get_current()


def encoder(value):
    value = uid_encoder(force_bytes(value))
    return value


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, *args, **kwargs):
    """
    Signal handler for password reset token creation.
    Sends password reset email with custom template.
    """
    frontend_url = getattr(settings, 'URL_FRONT', getattr(settings, 'FRONT_END_URL', 'http://localhost:3000'))
    email_plaintext_message = "{}change_password/{}/{}".format(
        frontend_url,
        encoder(reset_password_token.user.pk),
        reset_password_token.key
    )

    first_name = reset_password_token.user.first_name
    link = email_plaintext_message

    template_context = dict(
        first_name=first_name,
        link=link,
        website=frontend_url,
        site_name=current_site.domain
    )
    html_message = render_to_string('account/email/password_reset_email.html', template_context)
    plain_message = strip_tags(html_message)

    site_name = getattr(settings, 'SITE_NAME', 'AeroFinder')
    subject = 'Password Reset for {title}'.format(title=site_name)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', getattr(settings, 'EMAIL_HOST_USER', 'noreply@aerofinder.com'))
    to_email = reset_password_token.user.email

    msg = EmailMultiAlternatives(subject, plain_message, from_email, [to_email])
    msg.attach_alternative(html_message, "text/html")
    msg.send()
