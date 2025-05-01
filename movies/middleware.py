from django.shortcuts import redirect
from django.urls import resolve
from django.contrib import messages
from django.urls import reverse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class AdminAppSeparationMiddleware:
    """
    Middleware to ensure separation between admin users and regular app users.
    
    - Admin users (is_staff=True) can only access the admin interface and cannot use app features
    - Regular app users (with Profile role) cannot access the admin interface
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        try:
            # Get the resolved URL name
            url_name = resolve(request.path_info).url_name
            
            # Check if the URL is in the admin namespace
            is_admin_url = request.path.startswith('/admin/')
            
            # Special handling for static files, debug views, and other non-DB dependent views
            is_safe_path = (
                request.path.startswith('/static/') or
                request.path.startswith('/movies/admin/debug/') or
                request.path == '/' or
                'favicon' in request.path
            )
            
            # If it's a safe path, skip the complex middleware logic
            if is_safe_path:
                return self.get_response(request)
            
            # If the user is authenticated
            if request.user.is_authenticated:
                try:
                    # Admin users (staff) should not access app features
                    if request.user.is_staff and not request.user.is_superuser and not is_admin_url:
                        # Redirect admin users back to the admin site if they try to access app features
                        messages.warning(request, "Admin users cannot access app features. Please use the admin interface.")
                        return redirect('/admin/')
                        
                    # App users cannot access admin features
                    if not request.user.is_staff and is_admin_url:
                        # Redirect app users back to the home page if they try to access admin features
                        messages.warning(request, "You don't have permission to access the admin site.")
                        return redirect('/')
                except Exception as e:
                    # Log the error but don't crash the middleware
                    logger.error(f"Error in AdminAppSeparationMiddleware: {str(e)}")
            
            # Clean up any stale database connections
            from django.db import connection
            if connection.connection is not None and hasattr(connection, 'is_usable'):
                if not connection.is_usable():
                    connection.close()
        except Exception as e:
            # Log the error but don't crash the middleware
            logger.error(f"Unexpected error in AdminAppSeparationMiddleware: {str(e)}")
        
        response = self.get_response(request)
        return response 