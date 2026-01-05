from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from .models import AuditLog
from threading import local
from django.conf import settings

# Thread-local storage for request data
_thread_locals = local()


def set_current_request(request):
    """
    Store current request in thread-local storage
    Call this in middleware
    """
    _thread_locals.request = request


def get_current_request():
    """Get current request from thread-local storage"""
    return getattr(_thread_locals, 'request', None)


def get_current_user():
    """Get current user from request"""
    request = get_current_request()
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        return request.user
    return None


def get_request_metadata():
    """Extract IP and user agent from request"""
    request = get_current_request()
    ip_address = None
    user_agent = None

    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')

    return ip_address, user_agent


def get_model_data(instance, exclude_fields=None):
    """Extract all field data from model instance"""
    if exclude_fields is None:
        exclude_fields = ['id', 'created_at', 'updated_at', 'password']

    data = {}
    for field in instance._meta.fields:
        if field.name in exclude_fields:
            continue

        # Skip relation fields
        if field.is_relation:
            continue

        try:
            value = getattr(instance, field.name)

            # Convert to serializable format
            if hasattr(value, 'isoformat'):  # DateTime
                data[field.name] = value.isoformat()
            elif value is None:
                data[field.name] = None
            else:
                data[field.name] = str(value)
        except Exception:
            continue

    return data


# Store original instance data before save
@receiver(pre_save)
def store_pre_save_instance(sender, instance, **kwargs):
    """
    Store instance data before save for comparison
    Only track models in AUDIT_LOG_MODELS setting
    """

    # Skip AuditLog itself
    if sender == AuditLog:
        return

    # Check if model should be tracked
    audit_models = getattr(settings, 'AUDIT_LOG_MODELS', None)
    if audit_models and sender.__name__ not in audit_models:
        return

    # If instance has pk, it's an update - store old data
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._pre_save_instance = old_instance
        except sender.DoesNotExist:
            pass


@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    """
    Automatically log model creation and updates
    """

    # Skip AuditLog itself to prevent infinite loop
    if sender == AuditLog:
        return

    # Check if model should be tracked
    audit_models = getattr(settings, 'AUDIT_LOG_MODELS', None)
    if audit_models and sender.__name__ not in audit_models:
        return

    user = get_current_user()
    ip_address, user_agent = get_request_metadata()

    if created:
        # CREATE action
        after_data = get_model_data(instance)

        AuditLog.objects.create(
            user=user,
            action='create',
            model_name=sender.__name__,
            object_id=str(instance.pk),
            object_repr=str(instance),
            after_data=after_data,
            description=f"Created {sender.__name__}: {instance}",
            ip_address=ip_address,
            user_agent=user_agent
        )
    else:
        # UPDATE action
        after_data = get_model_data(instance)
        before_data = {}

        # Get before data if available
        if hasattr(instance, '_pre_save_instance'):
            before_data = get_model_data(instance._pre_save_instance)
            delattr(instance, '_pre_save_instance')

        # Only log if there are actual changes
        if before_data and before_data != after_data:
            AuditLog.objects.create(
                user=user,
                action='update',
                model_name=sender.__name__,
                object_id=str(instance.pk),
                object_repr=str(instance),
                before_data=before_data,
                after_data=after_data,
                description=f"Updated {sender.__name__}: {instance}",
                ip_address=ip_address,
                user_agent=user_agent
            )


@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    """
    Automatically log model deletion
    """

    # Skip AuditLog itself
    if sender == AuditLog:
        return

    # Check if model should be tracked
    audit_models = getattr(settings, 'AUDIT_LOG_MODELS', None)
    if audit_models and sender.__name__ not in audit_models:
        return

    user = get_current_user()
    ip_address, user_agent = get_request_metadata()

    before_data = get_model_data(instance)

    AuditLog.objects.create(
        user=user,
        action='delete',
        model_name=sender.__name__,
        object_id=str(instance.pk),
        object_repr=str(instance),
        before_data=before_data,
        description=f"Deleted {sender.__name__}: {instance}",
        ip_address=ip_address,
        user_agent=user_agent
    )


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """
    Automatically log user login
    """
    ip_address = None
    user_agent = None

    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')

    AuditLog.objects.create(
        user=user,
        action='login',
        description=f"User {user.username} logged in",
        ip_address=ip_address,
        user_agent=user_agent
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """
    Automatically log user logout
    """
    if user is None:
        return

    ip_address = None
    user_agent = None

    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')

    AuditLog.objects.create(
        user=user,
        action='logout',
        description=f"User {user.username} logged out",
        ip_address=ip_address,
        user_agent=user_agent
    )
