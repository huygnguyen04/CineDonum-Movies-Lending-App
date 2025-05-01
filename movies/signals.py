from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile
from django.utils import timezone
from django.db import transaction, IntegrityError

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    # First check if a profile already exists for this user
    profile_exists = Profile.objects.filter(user=instance).exists()
    
    if created and not profile_exists:
        # If the user is newly created and doesn't have a profile, create one
        try:
            # Use atomic transaction with savepoint to handle potential race conditions
            with transaction.atomic():
                # Check again inside transaction to handle race conditions
                if not Profile.objects.filter(user=instance).exists():
                    # Set role to librarian for special accounts
                    role = 'librarian' if instance.email == 'movies.app.librarian@gmail.com' else 'patron'
                    
                    # Create profile with appropriate role
                    Profile.objects.create(user=instance, role=role)
        except IntegrityError:
            # Profile was created by another process between our checks
            pass
        except Exception as e:
            # If there's an error with date_joined field or other issues
            try:
                # Simpler approach without some fields
                profile = Profile(user=instance)
                profile.role = 'librarian' if instance.email == 'movies.app.librarian@gmail.com' else 'patron'
                profile.save(update_fields=['user', 'role'])
            except Exception as inner_e:
                # Last resort fallback - log error but don't crash
                print(f"Error creating profile: {str(inner_e)}")
    elif not profile_exists:
        # If the user already exists but doesn't have a profile, create one
        try:
            with transaction.atomic():
                if not Profile.objects.filter(user=instance).exists():
                    role = 'librarian' if instance.email == 'movies.app.librarian@gmail.com' else 'patron'
                    Profile.objects.create(user=instance, role=role)
        except IntegrityError:
            # Profile was created by another process
            pass
        except Exception as e:
            # Fallback approach
            try:
                profile = Profile(user=instance)
                profile.role = 'librarian' if instance.email == 'movies.app.librarian@gmail.com' else 'patron'
                profile.save(update_fields=['user', 'role'])
            except Exception as inner_e:
                print(f"Error creating profile: {str(inner_e)}")
    else:
        # If profile exists, just try to save it
        try:
            instance.profile.save()
        except (Profile.DoesNotExist, AttributeError):
            # Handle case where profile lookup fails
            pass
