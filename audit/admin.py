from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
import json
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'action', 'model_name', 'object_repr', 'timestamp']
    list_filter = ['action', 'timestamp', 'model_name']
    search_fields = ['user__username', 'user__email', 'model_name', 'object_id', 'object_repr']
    readonly_fields = ['user', 'action', 'model_name', 'object_id', 'object_repr',
                       'before_data_display', 'after_data_display', 'changes_display',
                       'description', 'ip_address', 'user_agent', 'timestamp']
    date_hierarchy = 'timestamp'

    fieldsets = (
        ('Action Information', {
            'fields': ('user', 'action', 'model_name', 'object_id', 'object_repr', 'timestamp')
        }),
        ('Changes', {
            'fields': ('before_data_display', 'after_data_display', 'changes_display', 'description')
        }),
        ('Request Information', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )

    def before_data_display(self, obj):
        if obj.before_data:
            formatted = json.dumps(obj.before_data, indent=2)
            return format_html('<pre style="background: #f4f4f4; padding: 10px;">{}</pre>', formatted)
        return '-'

    before_data_display.short_description = 'Before Data'

    def after_data_display(self, obj):
        if obj.after_data:
            formatted = json.dumps(obj.after_data, indent=2)
            return format_html('<pre style="background: #f4f4f4; padding: 10px;">{}</pre>', formatted)
        return '-'

    after_data_display.short_description = 'After Data'

    def changes_display(self, obj):
        changes = obj.get_changes()
        if changes:
            formatted = json.dumps(changes, indent=2)
            return format_html('<pre style="background: #fff3cd; padding: 10px;">{}</pre>', formatted)
        return 'No changes detected'

    changes_display.short_description = 'Changed Fields'

    def has_add_permission(self, request):
        # Prevent manual creation of audit logs
        return False

    def has_change_permission(self, request, obj=None):
        # Prevent editing of audit logs
        return False

    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete audit logs
        return request.user.is_superuser
