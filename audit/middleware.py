from audit.signals import set_current_request


class AuditLogMiddleware:
    """
    Middleware to capture current request for automatic audit logging
    This allows signals to access request data (user, IP, user agent)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store request in thread-local storage
        set_current_request(request)

        response = self.get_response(request)

        return response
