def user_type(request):
    """
    Add user type information to all templates
    """
    context = {
        'is_admin_user': False,
        'is_app_user': False
    }
    
    if request.user.is_authenticated:
        # Admin users
        if request.user.is_staff:
            context['is_admin_user'] = True
        # App users (with a profile)
        elif hasattr(request.user, 'profile'):
            context['is_app_user'] = True
    
    return context 