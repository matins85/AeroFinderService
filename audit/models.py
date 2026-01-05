from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('view', 'View'),
        ('login', 'Login'),
        ('logout', 'Logout'),
    ]

    # Who performed the action
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    # What was done
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, blank=True, null=True)
    object_id = models.CharField(max_length=100, blank=True, null=True)
    object_repr = models.CharField(max_length=255, blank=True, null=True,
                                   help_text="String representation of the object")

    # Changes (Before and After)
    before_data = models.JSONField(default=dict, blank=True, null=True, help_text="Data before the change")
    after_data = models.JSONField(default=dict, blank=True, null=True, help_text="Data after the change")

    # Additional metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Optional description
    description = models.TextField(blank=True, null=True, help_text="Optional description of the action")

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user']),
            models.Index(fields=['action']),
            models.Index(fields=['model_name']),
        ]
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        return f"{self.user} - {self.action} - {self.model_name} - {self.timestamp}"

    def get_changes(self):
        """
        Returns a dictionary of fields that changed
        """
        if not self.before_data or not self.after_data:
            return {}

        changes = {}
        for key in self.after_data.keys():
            if key in self.before_data:
                if self.before_data[key] != self.after_data[key]:
                    changes[key] = {
                        'before': self.before_data[key],
                        'after': self.after_data[key]
                    }
        return changes
