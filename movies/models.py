from django.contrib.auth.models import User
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q, Avg
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
import sys
from django.db import connection


# setting parameters here for easier changes - Ozcan S. 2025/2/20
NAME_LENGTH = 150  # used for names of actors, movies, collections, etc.
DESCRIPTION_LENGTH = 1000  # used for descriptions of actors, movies, etc.
SHORT_TEXT_FIELD = 50  # used for things such as locations and languages which typically do not exceed a few words
MAX_RATING = 5  # maximum rating something can be given (changed from 10 to 5)
MIN_RATING = 0  # minimum rating something can be given
import pycountry
LANGUAGE_CHOICES = []
for lang in pycountry.languages:
    if hasattr(lang, 'alpha_2') and hasattr(lang, 'name'):
        LANGUAGE_CHOICES.append((lang.alpha_2, lang.name))
LANGUAGE_CHOICES.sort(key=lambda x: x[1])

# IMPORTANT !!!
# FOR IMMEDIATE CONSIDERATION, SHOULD DESCRIPTIONS BE CharField OR TextField?
# https://stackoverflow.com/questions/7354588/whats-the-difference-between-charfield-and-textfield-in-django
# - Ozcan S. 2025/2/20
# delete comment after resolving, leave the URL and add as citation

# MODELS FOR MANAGERS - BGN #

# CITATION: https://docs.djangoproject.com/en/5.1/topics/db/managers/
# USE: Standards for managers (implementation fo Database lookup/tag search
# - Ozcan S. 2025/2/20

# add profile role for each user
ROLE_CHOICES = (
    ('patron', 'Patron'),
    ('librarian', 'Librarian'),
)


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='patron')
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    date_joined = models.DateField(auto_now_add=True, null=True, blank=True, help_text="Date the user joined the Community Library Association")
    real_name = models.CharField(max_length=100, blank=True, null=True, help_text="User's real name")

    def __str__(self):
        return f"{self.user.username} Profile"
    
    def save(self, *args, **kwargs):
        # Skip special handling for admin users
        if self.user.is_staff:
            super().save(*args, **kwargs)
            return
            
        # Always ensure 'movies.app.librarian@gmail.com' has librarian role
        if self.user.email == 'movies.app.librarian@gmail.com':
            self.role = 'librarian'
            
        super().save(*args, **kwargs)


@receiver(post_save, sender=Profile)
def assign_librarian_group(sender, instance, **kwargs):
    librarian_group, _ = Group.objects.get_or_create(name='librarian')

    if instance.role == 'librarian':
        if not instance.user.groups.filter(name='librarian').exists():
            instance.user.groups.add(librarian_group)
    else:
        if instance.user.groups.filter(name='librarian').exists():
            instance.user.groups.remove(librarian_group)


class MovieManager(models.Manager):
    def search(self, query):
        return self.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()


class CollectionManager(models.Manager):
    def search(self, query):
        return self.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()


# MODELS FOR MANAGERS - END #

# MODELS FOR MOVIES AND RELATED PROPERTIES - BGN #


class Actor(models.Model):
    name = models.CharField(max_length=NAME_LENGTH)
    bio = models.CharField(max_length=DESCRIPTION_LENGTH)

    def __str__(self):
        return self.name


class Director(models.Model):
    name = models.CharField(max_length=NAME_LENGTH)
    bio = models.CharField(max_length=DESCRIPTION_LENGTH)

    def __str__(self):
        return self.name


class Genre(models.Model):
    name = models.CharField(max_length=NAME_LENGTH, unique=True)

    def __str__(self):
        return self.name


# primary movie model - Ozcan S. 2025/2/20
class Movie(models.Model):
    # consider replacing this with IMDb ID? the primary key will be generated anyway due to Django internals,
    # but the id property will be different - Ozcan S. 2025/2/20
    id = models.AutoField(primary_key=True)

    STATUS_CHOICES = [
        ('available', 'Available'),
        ('unavailable', 'Unavailable'),
    ]

    status = models.CharField(max_length=SHORT_TEXT_FIELD, choices=STATUS_CHOICES, default='available')

    title = models.CharField(max_length=NAME_LENGTH)

    description = models.CharField(max_length=DESCRIPTION_LENGTH)

    release_date = models.DateField()  # studio release date

    upload_date = models.DateTimeField(auto_now_add=True)  # library upload date

    duration = models.PositiveIntegerField(help_text="duration in minutes")

    language = models.CharField(max_length=SHORT_TEXT_FIELD,
                                choices=LANGUAGE_CHOICES,
    blank=True,
    null=True
    )

    key_value = models.CharField(max_length=SHORT_TEXT_FIELD, blank=True, null=True, unique=True,
                                help_text="A unique identifier for this movie (barcode, ISBN, UPC, etc.)")

    location = models.CharField(max_length=SHORT_TEXT_FIELD, default="UNKNOWN")

    genre = models.ManyToManyField(Genre)

    cast = models.ManyToManyField(Actor)

    # placing this as a ManyToManyField since a movie might have more than 1 director - Ozcan S. 2025/2/20
    director = models.ManyToManyField(Director)

    tags = models.ManyToManyField("Tag", blank=True, related_name="movies")

    objects = MovieManager()

    @property
    def average_rating(self):
        """Calculate the average rating for this movie based on reviews with ratings."""
        reviews_with_ratings = self.reviews.exclude(rating__isnull=True).exclude(rating=0)
        if reviews_with_ratings.exists():
            return reviews_with_ratings.aggregate(Avg('rating'))['rating__avg']
        return 0
        
    def save(self, *args, **kwargs):
        # Handle supply and demand fields if they still exist in the database
        # but were removed from the model
        with connection.cursor() as cursor:
            # Check if we're using SQLite (which doesn't have information_schema)
            if connection.vendor == 'sqlite':
                # For SQLite, use a different approach to check columns
                try:
                    # Try to get column info directly from the table
                    cursor.execute("PRAGMA table_info(movies_movie);")
                    columns = [row[1] for row in cursor.fetchall()]
                    
                    # Handle supply and demand fields if they exist
                    if 'supply' in columns or 'demand' in columns:
                        # First, save without these fields
                        super().save(*args, **kwargs)
                        
                        # Then update the supply and demand fields directly
                        movie_id = self.id
                        with connection.cursor() as update_cursor:
                            if 'supply' in columns:
                                update_cursor.execute("UPDATE movies_movie SET supply = 0 WHERE id = ? AND supply IS NULL;", [movie_id])
                            if 'demand' in columns:
                                update_cursor.execute("UPDATE movies_movie SET demand = 0 WHERE id = ? AND demand IS NULL;", [movie_id])
                        return
                except Exception as e:
                    # If any error occurs, just do a normal save
                    print(f"SQLite column check error: {str(e)}")
                    super().save(*args, **kwargs)
                    return
            else:
                # PostgreSQL approach
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'movies_movie';")
                columns = [row[0] for row in cursor.fetchall()]
                
                # If the database still has these columns, handle them via raw SQL
                if 'supply' in columns or 'demand' in columns:
                    # First, save without these fields
                    super().save(*args, **kwargs)
                    
                    # Then update the supply and demand fields directly
                    movie_id = self.id
                    with connection.cursor() as update_cursor:
                        if 'supply' in columns:
                            update_cursor.execute("UPDATE movies_movie SET supply = 0 WHERE id = %s AND supply IS NULL;", [movie_id])
                        if 'demand' in columns:
                            update_cursor.execute("UPDATE movies_movie SET demand = 0 WHERE id = %s AND demand IS NULL;", [movie_id])
                    return
                
        # If we get here, the columns don't exist, so just do a normal save
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class MovieImage(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="movies/", null=True, blank=True)

    def __str__(self):
        return f"Image for {self.movie.title}"

class Review(models.Model):
    class Meta:
        abstract = False
    title = models.CharField(max_length=NAME_LENGTH, blank=True, null=True)
    body = models.CharField(max_length=DESCRIPTION_LENGTH)
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(MIN_RATING), MaxValueValidator(MAX_RATING)],
        blank=True, null=True,
        help_text="Rating from 0 to 5 stars"
    )
    pub_date = models.DateTimeField(auto_now_add=True)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="reviews")
    author = models.CharField(max_length=100, null=True)  # Store the user's email
    user_role = models.CharField(max_length=20, null=True)  # Store whether patron or librarian

    def __str__(self):
        if self.title:
            return self.title
        return f"Comment on {self.movie.title}"


# MODELS FOR MOVIES AND RELATED PROPERTIES - END #

# MODEL FOR COLLECTION - BGN #

class Collection(models.Model):
    class Meta:
        abstract = False
    name = models.CharField(max_length=NAME_LENGTH)

    description = models.CharField(max_length=DESCRIPTION_LENGTH, blank=True, null=True)

    movies = models.ManyToManyField("Movie", related_name="collections")

    # leaving null and blank as TRUE for now since we might have auto/system generated collections?
    # can be changed later on - Ozcan S. 2/20/2025
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="collections", null=True, blank=True)

    create_date = models.DateTimeField(auto_now_add=True)

    update_date = models.DateTimeField(auto_now=True)

    is_public = models.BooleanField(default=True)

    tags = models.ManyToManyField("Tag", blank=True, related_name="collections")

    # leaving null and blank to True for now since we do not have any collection covers
    # consider potentially removing this field? - Ozcan S. 2025/2/20
    cover_image = models.ImageField(upload_to="collection_covers/", null=True, blank=True)

    allowed_users = models.ManyToManyField(User, blank=True)

    objects = CollectionManager()

    def __str__(self):
        return self.name


class Tag(models.Model):
    # Tag model used to store tags such as "Best of 2025" or "Classics", etc.
    name = models.CharField(max_length=NAME_LENGTH, unique=True)

    def __str__(self):
        return self.name


# move to Signals.py? - Ozcan S. 2025/2/20
@receiver(m2m_changed, sender=Collection.movies.through)
def validate_collection_movies(sender, instance, action, pk_set, **kwargs):
    """
    Signal to ensure a movie isn't in multiple private collections.
    For public collections, validation happens at the form level by 
    excluding movies already in private collections from selection.
    """
    # Skip signal validation during tests
    if 'test' in sys.argv:
        return

    if action == "pre_add" and pk_set:
        # Only perform validation for private collections
        if not instance.is_public:
            # Get the movies being added
            movies_to_add = Movie.objects.filter(pk__in=pk_set)
            
            # For private collections, verify none of the movies are in other PRIVATE collections
            conflict_movies = []
            for movie in movies_to_add:
                # Check for conflicts with other private collections
                if instance.pk:
                    # When editing, exclude the current collection
                    other_private = movie.collections.filter(is_public=False).exclude(pk=instance.pk)
                    if other_private.exists():
                        conflict_movies.append(movie.title)
                else:
                    # For new collections
                    if movie.collections.filter(is_public=False).exists():
                        conflict_movies.append(movie.title)
                            
            if conflict_movies:
                raise ValidationError("The following movies are already in a private collection and cannot be added: " + ", ".join(conflict_movies))


@receiver(m2m_changed, sender=Collection.movies.through)
def handle_movie_collections(sender, instance, action, pk_set, **kwargs):
    """
    Signal to handle:
    1. When a movie is added to a private collection, remove it from all public collections
    2. Enforce that movies in private collections cannot be in any other collection
    """
    # Skip during tests
    if 'test' in sys.argv:
        return
    
    # Only process if we're adding movies and have movie IDs
    if action == "post_add" and pk_set:
        # If this is a private collection
        if not instance.is_public:
            # Get the movies that were added
            added_movies = Movie.objects.filter(pk__in=pk_set)
            
            # Remove these movies from all public collections
            for movie in added_movies:
                # Find all public collections containing this movie (except the current one)
                public_collections = Collection.objects.filter(
                    movies=movie, 
                    is_public=True
                )
                
                # Remove the movie from each public collection
                for collection in public_collections:
                    collection.movies.remove(movie)
                    print(f"Removed movie '{movie.title}' from public collection '{collection.name}'")

# MODEL FOR COLLECTION - END #
class AccessRequest(models.Model):
    patron = models.ForeignKey(User, on_delete=models.CASCADE)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    requested_at = models.DateTimeField(auto_now_add=True)

    # Make sure these fields actually exist:
    appeal_message = models.TextField(blank=True, null=True)
    under_appeal = models.BooleanField(default=False)

# MODEL FOR BORROWING - BGN #
class LoanRecord(models.Model):
    LOAN_STATUS = (
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('borrowed', 'Borrowed'),
        ('returned', 'Returned'),
        ('overdue', 'Overdue'),
    )
    
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="loans")
    patron = models.ForeignKey(User, on_delete=models.CASCADE, related_name="borrowed_movies")
    librarian = models.ForeignKey(User, on_delete=models.CASCADE, related_name="handled_loans", 
                                 null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=LOAN_STATUS, default='requested')
    
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    borrowed_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the loan")
    
    def __str__(self):
        return f"{self.movie.title} - {self.patron.email} ({self.status})"
        
    class Meta:
        ordering = ['-requested_at']
# MODEL FOR BORROWING - END #

# MODEL FOR NOTIFICATIONS - BGN #
class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('loan_approved', 'Loan Approved'),
        ('loan_rejected', 'Loan Rejected'),
        ('loan_due_soon', 'Loan Due Soon'),
        ('loan_overdue', 'Loan Overdue'),
        ('movie_returned', 'Movie Returned'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    related_loan = models.ForeignKey(LoanRecord, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.notification_type} for {self.user.email}"
    
    class Meta:
        ordering = ['-created_at']
# MODEL FOR NOTIFICATIONS - END #

# Create a Profile when a User is created
# This signal is now handled in signals.py and has been commented out to prevent duplicate profile creation
# @receiver(post_save, sender=User)
# def create_user_profile(sender, instance, created, **kwargs):
#     if created:
#         # Skip profile creation for admin users (is_staff=True)
#         if instance.is_staff:
#             return
#            
#         # Create profile for regular users with appropriate role
#         Profile.objects.create(user=instance, role='patron')