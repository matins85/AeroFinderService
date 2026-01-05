from rest_framework import permissions


class OwnerOrReadOnly(permissions.BasePermission):
    """Permission to allow owners to edit their own resources"""
    
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Check if object has user attribute
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # Check if object has wallet attribute
        if hasattr(obj, 'wallet') and hasattr(obj.wallet, 'user'):
            return obj.wallet.user == request.user
        
        return False

