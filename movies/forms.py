from django import forms
from .models import Profile, MovieImage, Movie, Collection
from django.contrib.auth.models import User

class ProfilePictureForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['profile_picture', 'real_name']
        widgets = {
            'profile_picture': forms.FileInput(attrs={'class': 'custom-file-input'}),
            'real_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your full name'}),
        }


class MovieImageForm(forms.ModelForm):
    class Meta:
        model = MovieImage
        fields = ['image']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'custom-file-input'}),
        }

class MovieForm(forms.ModelForm):
    key_value = forms.CharField(
        max_length=50, 
        required=False,
        help_text="A unique identifier for this movie (will be auto-generated if left blank)",
        widget=forms.TextInput(attrs={'placeholder': 'Leave blank for auto-generation'})
    )
    
    class Meta:
        model = Movie
        fields = [
            'title',
            'description',
            'release_date',
            'duration',
            'language',
            'key_value',
            'location',
        ]
        widgets = {
            'release_date': forms.DateInput(attrs={'type': 'date'}),
        }
        
    def save(self, commit=True):
        movie = super().save(commit=False)
        # Handle removed fields explicitly - set them to None
        # This ensures we don't try to save values for fields that aren't in the model
        # but might still exist in the database
        if hasattr(movie, 'supply'):
            movie.supply = None
        if hasattr(movie, 'demand'):
            movie.demand = None
            
        if commit:
            movie.save()
            self.save_m2m()
        return movie

class CollectionForm(forms.ModelForm):
    movies = forms.ModelMultipleChoiceField(
        queryset=Movie.objects.none(),  # Initialize empty, will be populated in __init__
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    class Meta:
        model = Collection
        # Include allowed_users here for librarians if you want that field saved
        fields = [
            'name',
            'description',
            'is_public',
            'tags',
            'movies',
        ]
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(CollectionForm, self).__init__(*args, **kwargs)
        
        try:
            # Filter out movies that are already in private collections
            from django.db import connection
            connection.ensure_connection()  # Ensure we have an active connection
            
            # Use a safer query approach that's less likely to cause connection issues
            from django.db.models import Q
            
            # When editing a collection, don't exclude movies already in this collection
            if self.instance.pk:
                # For existing collections, disable the is_public field to prevent type changes
                self.fields['is_public'].disabled = True
                
                try:
                    movies_in_this_collection = list(self.instance.movies.values_list('pk', flat=True))
                    
                    if not self.instance.is_public:
                        # If this is a private collection, handle its existing movies
                        private_collection_movies = Movie.objects.filter(
                            collections__is_public=False
                        ).exclude(
                            pk__in=movies_in_this_collection
                        ).values_list('pk', flat=True)
                        
                        self.fields['movies'].queryset = Movie.objects.exclude(
                            pk__in=private_collection_movies
                        )
                    else:
                        # If this is a public collection, exclude all movies in private collections
                        private_collection_movies = Movie.objects.filter(
                            collections__is_public=False
                        ).values_list('pk', flat=True)
                        
                        self.fields['movies'].queryset = Movie.objects.exclude(
                            pk__in=private_collection_movies
                        )
                except Exception as e:
                    # If any error occurs, fall back to showing all movies
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error loading movies for collection edit: {e}")
                    self.fields['movies'].queryset = Movie.objects.all()
            else:
                # For new collections, exclude all movies in private collections
                try:
                    private_collection_movies = Movie.objects.filter(
                        collections__is_public=False
                    ).values_list('pk', flat=True)
                    
                    self.fields['movies'].queryset = Movie.objects.exclude(
                        pk__in=private_collection_movies
                    )
                except Exception as e:
                    # If any error occurs, fall back to showing all movies
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error loading movies for new collection: {e}")
                    self.fields['movies'].queryset = Movie.objects.all()
            
            # Add user-specific fields and permissions
            if user:
                if user.profile.role == 'patron':
                    # Patrons can only create public collections.
                    self.fields['is_public'].initial = True
                    self.fields['is_public'].disabled = True
                elif user.profile.role == 'librarian':
                    # For librarians, add allowed_users to choose which patrons can view a private collection.
                    try:
                        self.fields['allowed_users'] = forms.ModelMultipleChoiceField(
                            queryset=User.objects.filter(profile__role='patron'),
                            widget=forms.CheckboxSelectMultiple,
                            required=False,
                            help_text="Select patrons who should have access if this collection is private."
                        )
                        # Include allowed_users in the Meta fields so it gets saved.
                        if 'allowed_users' not in self.Meta.fields:
                            self.Meta.fields.append('allowed_users')
                    except Exception as e:
                        # If this fails, just skip adding the allowed_users field
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Error adding allowed_users field: {e}")
                        
        except Exception as e:
            # If any error occurs in the main setup, ensure we have a basic working form
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error setting up CollectionForm: {e}")
            self.fields['movies'].queryset = Movie.objects.all()
    
    def clean(self):
        cleaned_data = super().clean()
        is_public = cleaned_data.get('is_public')
        movies = cleaned_data.get('movies')
        
        if movies and not is_public:
            # For private collections, if adding movies that are in public collections,
            # add a warning that they will be removed from those collections
            try:
                public_movies = []
                for movie in movies:
                    if movie.collections.filter(is_public=True).exists():
                        public_movies.append(movie.title)
                        
                if public_movies:
                    self.add_warning = f"Note: The following movies will be removed from all public collections when added here: {', '.join(public_movies)}"
            except Exception as e:
                # If the check fails, just skip the warning
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error checking for public movies: {e}")
                    
        return cleaned_data
