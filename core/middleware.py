from django.utils.deprecation import MiddlewareMixin


class DisableCSRFForPaymentAPI(MiddlewareMixin):
    """Disable CSRF protection for payment API endpoints"""
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Disable CSRF for all payment API endpoints
        if request.path.startswith('/api/payments/'):
            setattr(request, '_dont_enforce_csrf_checks', True)
        return None 