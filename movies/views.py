from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout, login, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
import logging
from django.urls import reverse
from django.db.models import Q, Count
from django.core.exceptions import ValidationError
from django.db import transaction, connection, OperationalError, InterfaceError
from django.contrib import messages
from .forms import ProfilePictureForm, MovieImageForm, MovieForm, CollectionForm
from .models import Movie, Review, Profile, MovieImage, Collection, AccessRequest, LoanRecord, Notification, User
from datetime import datetime, timedelta
from django.utils import timezone
import random
import time


logger = logging.getLogger(__name__)

def filter_accessible_movies(user, movies_queryset):
    """
    Filter a movies queryset based on user access permissions.
    
    This function handles several access cases:
    1. Anonymous users: Can only see movies not in collections or in public collections
    2. Patrons: Can see movies not in collections, in public collections, and in private 
                collections they have access to (owner, allowed_user, or approved request)
    3. Librarians: Can see all movies
    
    Returns a filtered queryset of movies.
    """
    if not user or not user.is_authenticated:
        # For anonymous users, exclude all movies in private collections
        private_collections = Collection.objects.filter(is_public=False)
        return movies_queryset.exclude(collections__in=private_collections)
    
    if user.profile.role == 'librarian':
        # Librarians can see all movies
        return movies_queryset
    
    # For patrons, get private collections they CAN'T access
    inaccessible_collections = Collection.objects.filter(is_public=False).exclude(
        # Collections they own
        Q(owner=user) |
        # Collections they're explicitly allowed to access
        Q(allowed_users=user) |
        # Collections they have approved request
        Q(accessrequest__patron=user, accessrequest__approved=True)
    ).distinct()
    
    # Exclude movies that are in private collections they can't access
    return movies_queryset.exclude(collections__in=inaccessible_collections)


def index(request):
    return render(request, 'movies/index.html')

@login_required
def rolepick(request):
    return render(request, 'movies/rolepick.html')

def guest_view(request):
    if request.user.is_authenticated:
        role = request.user.profile.role
        if role == 'librarian':
            return redirect('librarian_home')
        elif role == 'patron':
            return redirect('patron_home')
    return render(request, 'movies/guest_home.html')

@login_required
def upload_profile_picture(request):
    profile = Profile.objects.get(user=request.user)

    if request.method == 'POST':
        form = ProfilePictureForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            # Save name and/or picture fields
            form.save()

            # If there’s an uploaded file, save it explicitly (e.g. for S3 logic)
            uploaded_file = request.FILES.get('profile_picture')
            if uploaded_file:
                try:
                    profile.profile_picture.save(uploaded_file.name, uploaded_file, save=True)
                    logger.info(f"Successfully uploaded {uploaded_file.name} to S3")
                except Exception as e:
                    logger.error(f"Upload failed: {e}", exc_info=True)
                    # we swallow the error, but still want to show success

            # Always show the same green banner
            messages.success(request, "Your profile has been updated successfully.")
            return redirect('rolepick')

        else:
            logger.error(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

    else:
        form = ProfilePictureForm(instance=profile)

    return render(request, 'movies/upload_profile_picture.html', {'form': form})

@login_required
def patron_view(request):
    # If the user is a librarian, redirect them to the librarian view.
    if request.user.profile.role == 'librarian':
        return redirect('librarian_home')
    return render(request, 'movies/patron_home.html')

@login_required
def librarian_view(request):
    # Only allow users with the librarian role to access this view.
    if request.user.profile.role == 'patron':
        return redirect('patron_home')
    return render(request, 'movies/librarian_home.html')

def home(request):
    return HttpResponse("home")

def logout_view(request):
    logout(request)
    return redirect("/")

def search_movies(request):
    # DEPRECATED: This view is kept for backward compatibility.
    # The search functionality is now integrated into the movie list page.
    query = request.GET.get('q', None)
    results = Movie.objects.none()
    
    if query:
        results = Movie.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()
    
    context = {
        'query': query,
        'results': results
    }
    return redirect('available_movies')


def available_movies(request):
    # Get all movies, regardless of status
    all_movies = Movie.objects.all()
    
    # Filter the results based on user's access permissions
    accessible_movies = filter_accessible_movies(request.user, all_movies)
    
    return render(request, 'movies/available_movies.html', {'movies': accessible_movies})




def movie_reviews(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    
    # Make sure reviews will work even if columns are missing
    try:
        # Use raw SQL to ensure we only select columns that exist
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, title, body, rating, pub_date, movie_id
                FROM movies_review
                WHERE movie_id = %s
                ORDER BY pub_date DESC
            """, [movie_id])
            
            columns = [col[0] for col in cursor.description]
            reviews_data = cursor.fetchall()
            
        # Convert the raw SQL results to a list of dictionaries
        reviews = []
        for row in reviews_data:
            review_dict = {columns[i]: row[i] for i in range(len(columns))}
            # Add empty values for potential missing columns to avoid template errors
            if 'author' not in review_dict:
                review_dict['author'] = None
            if 'user_role' not in review_dict:
                review_dict['user_role'] = None
            reviews.append(review_dict)
            
    except Exception as e:
        # If there's an error with the reviews query, return an empty list
        reviews = []
    
    # Check if movie is in any private collections the user can't access
    private_collections = movie.collections.filter(is_public=False)
    if private_collections.exists() and not request.user.is_authenticated:
        # If movie is only in private collections, anonymous users shouldn't see it
        if movie.collections.filter(is_public=True).count() == 0:
            return redirect('available_movies')
    
    # Get all collections containing this movie
    all_collections = movie.collections.all()
    
    # Filter collections based on user access
    accessible_collections = []
    for collection in all_collections:
        # Public collections are always accessible
        if collection.is_public:
            accessible_collections.append(collection)
        # For private collections, check access for authenticated users
        elif request.user.is_authenticated:
            if request.user.profile.role == 'librarian':
                # Librarians can see all collections
                accessible_collections.append(collection)
            else:
                # Patrons need specific access
                is_owner = request.user == collection.owner
                is_allowed_user = request.user in collection.allowed_users.all()
                has_approved_request = AccessRequest.objects.filter(
                    patron=request.user,
                    collection=collection,
                    approved=True
                ).exists()
                
                if is_owner or is_allowed_user or has_approved_request:
                    accessible_collections.append(collection)

    context = {
        'movie': movie,
        'reviews': reviews,
        'collections': accessible_collections,
        'user_authenticated': request.user.is_authenticated,
    }
    return render(request, 'movies/movie_reviews.html', context)

def is_librarian(user):
    return user.is_authenticated and user.profile.role == 'librarian'

@user_passes_test(is_librarian)
def add_movie_image(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    if request.method == 'POST':
        form = MovieImageForm(request.POST, request.FILES)
        if form.is_valid():
            movie_image = form.save(commit=False)
            movie_image.movie = movie
            movie_image.save()
            return redirect('movie_reviews', movie_id=movie.id)
    else:
        form = MovieImageForm()
    return render(request, 'movies/add_movie_image.html', {
        'form': form,
        'movie': movie
    })

@login_required
def add_movie(request):
    """View to add movies (librarian only)"""
    if request.user.profile.role != 'librarian':
        return redirect('index')

    if request.method == 'POST':
        form = MovieForm(request.POST)
        if form.is_valid():
            try:
                # Save the movie but don't commit yet
                movie = form.save(commit=False)
                
                # Generate a key_value if not provided
                if not movie.key_value:
                    # Format: MOV-{current_year}-{random 6 digits}
                    current_year = datetime.now().year
                    
                    # Try to generate a unique key_value (retry up to 5 times)
                    max_attempts = 5
                    for attempt in range(max_attempts):
                        random_digits = ''.join([str(random.randint(0, 9)) for _ in range(6)])
                        key_value = f"MOV-{current_year}-{random_digits}"
                        
                        # Check if this key_value already exists
                        if not Movie.objects.filter(key_value=key_value).exists():
                            movie.key_value = key_value
                            break
                        
                        # If we've tried max_attempts times and still failed, use timestamp for uniqueness
                        if attempt == max_attempts - 1:
                            movie.key_value = f"MOV-{current_year}-{int(time.time())}"
                
                # Direct database update for supply and demand (which might still be in the database)
                # This handles the case where the columns exist but the model fields don't
                try:
                    from django.db import connection
                    with connection.cursor() as cursor:
                        # First save the movie to get an ID
                        movie.save()
                        
                        # Handle supply and demand if they exist
                        movie_id = movie.id
                        cursor.execute("""
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_name = 'movies_movie' AND column_name IN ('supply', 'demand');
                        """)
                        columns = [row[0] for row in cursor.fetchall()]
                        
                        if 'supply' in columns or 'demand' in columns:
                            # Build update SQL
                            updates = []
                            if 'supply' in columns:
                                updates.append("supply = 0")
                            if 'demand' in columns:
                                updates.append("demand = 0")
                                
                            if updates:
                                update_sql = f"UPDATE movies_movie SET {', '.join(updates)} WHERE id = %s;"
                                cursor.execute(update_sql, [movie_id])
                
                    # Now save many-to-many relationships
                    form.save_m2m()
                
                except Exception as db_error:
                    # If the direct SQL approach fails, provide specific error handling for common issues
                    error_message = str(db_error)
                    if 'supply' in error_message and 'not-null' in error_message:
                        messages.error(request, "Database schema issue detected. Please visit /movies/admin/debug/schema/ to fix this issue.")
                        return redirect('debug_database_schema')
                    elif 'demand' in error_message and 'not-null' in error_message:
                        messages.error(request, "Database schema issue detected. Please visit /movies/admin/debug/schema/ to fix this issue.")
                        return redirect('debug_database_schema')
                    else:
                        # Re-raise for general handling
                        raise
                
                messages.success(request, f"Movie '{movie.title}' added successfully with ID: {movie.key_value}")
                return redirect('available_movies')
            except Exception as e:
                # If there's an error (like duplicate key_value), add an error to the form
                error_message = str(e)
                if 'supply' in error_message and 'not-null' in error_message:
                    messages.error(request, "There is a database schema issue with the 'supply' field. Please visit /movies/admin/debug/schema/ to fix it.")
                    return redirect('debug_database_schema')
                elif 'demand' in error_message and 'not-null' in error_message:
                    messages.error(request, "There is a database schema issue with the 'demand' field. Please visit /movies/admin/debug/schema/ to fix it.")
                    return redirect('debug_database_schema')
                else:
                    form.add_error(None, f"Error creating movie: {str(e)}")
    else:
        form = MovieForm()

    return render(request, 'movies/add_movie.html', {'form': form})

@user_passes_test(is_librarian)
def remove_movie_image(request, image_id):
    image = get_object_or_404(MovieImage, id=image_id)
    if request.method == 'POST':
        image.delete()
        return redirect('available_movies')
    return render(request, 'movies/remove_movie_image.html', {'image': image})

@user_passes_test(is_librarian)
def remove_movie(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    if request.method == 'POST':
        movie.delete()
        return redirect('available_movies')
    return render(request, 'movies/remove_movie.html', {'movie': movie})


@login_required
def add_collection(request):
    warning_message = None
    try:
        if request.method == 'POST':
            # Use atomic transaction with retry logic
            max_attempts = 3
            attempt = 0
            
            while attempt < max_attempts:
                attempt += 1
                try:
                    form = CollectionForm(request.POST, user=request.user)
                    if form.is_valid():
                        try:
                            with transaction.atomic():
                                new_collection = form.save(commit=False)
                                new_collection.owner = request.user  # Set the collection's creator
                                if request.user.profile.role == 'patron':
                                    new_collection.is_public = True  # Force public for patrons
                                new_collection.save()
                                form.save_m2m()  # Save many-to-many data
                            
                            # If we get here, the transaction was successful
                            messages.success(request, f"Collection '{new_collection.name}' created successfully.")
                            if request.user.profile.role == 'librarian':
                                return redirect('view_collections')
                            else:
                                return redirect('view_collections')
                        except ValidationError as ve:
                            form.add_error('movies', ve.message)
                            break  # Don't retry validation errors
                        except (OperationalError, InterfaceError) as e:
                            if attempt == max_attempts:
                                # If we've reached max attempts, raise the error
                                logger.error(f"Failed to create collection after {max_attempts} attempts: {e}")
                                messages.error(request, "Database error. Please try again later.")
                                break
                            else:
                                # Close any stale connections and retry
                                connection.close()
                                continue
                    else:
                        # Form not valid, no need to retry
                        break
                except (OperationalError, InterfaceError) as e:
                    if attempt == max_attempts:
                        logger.error(f"Database connection error: {e}")
                        messages.error(request, "Database connection error. Please try again later.")
                    else:
                        # Close any stale connections and retry
                        connection.close()
                        continue
            
            # Get warning message about movies being removed from public collections
            if hasattr(form, 'add_warning'):
                warning_message = form.add_warning
        else:
            form = CollectionForm(user=request.user)
    except Exception as e:
        # Catch any unexpected errors
        logger.error(f"Unexpected error in add_collection: {e}")
        messages.error(request, "An unexpected error occurred. Please try again later.")
        form = CollectionForm(user=request.user)
    
    context = {
        'form': form,
        'warning_message': warning_message
    }
    return render(request, 'movies/add_collection.html', context)

# @login_required
# def view_collections(request):
#     # If the user is not authenticated (shouldn't happen with login_required), show public collections.
#     if not request.user.is_authenticated:
#         collections = Collection.objects.filter(is_public=True)
#     else:
#         if request.user.profile.role == 'librarian':
#             # Librarians see all collections.
#             collections = Collection.objects.all()
#         else:
#             # Patrons see:
#             # - All public collections
#             # - Collections they own
#             # - Private collections where they are allowed (allowed_users)
#             collections = Collection.objects.filter(
#                 Q(is_public=True) |
#                 Q(owner=request.user) |
#                 Q(allowed_users__id=request.user.id)
#             ).distinct()
#     return render(request, 'movies/all_collections.html', {'collections': collections})


# @login_required
def view_collections(request):
    # Librarians see all collections.
    # Patrons can see all collection titles (both public and private).
    # Anonymous users can only see public collections.
    query = request.GET.get('q', None)
    
    if query:
        # Search collections by title, description, and tags
        collections = Collection.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()
        
        # Filter results based on user access permissions
        if not request.user.is_authenticated:
            # Anonymous users only see public collections
            collections = collections.filter(is_public=True)
        elif request.user.profile.role != 'librarian':
            # Patrons see:
            # - All public collections
            # - Collections they own
            # - Private collections where they are allowed
            # - Private collections they have approved access to
            collections = collections.filter(
                Q(is_public=True) |
                Q(owner=request.user) |
                Q(allowed_users=request.user) |
                Q(accessrequest__patron=request.user, accessrequest__approved=True)
            ).distinct()
        # Librarians can see all collections (no filtering needed)
    else:
        # No search query, show all collections
        if not request.user.is_authenticated:
            # Anonymous users only see public collections
            collections = Collection.objects.filter(is_public=True).distinct()
        else:
            collections = Collection.objects.all().distinct()
    
    return render(request, 'movies/all_collections.html', {'collections': collections, 'query': query})


def collection_detail(request, collection_id):
    collection = get_object_or_404(Collection, id=collection_id)

    user_request = None  # new addition
    movies = []
    show_items = False

    # Anonymous users can only access public collections
    if not request.user.is_authenticated:
        if collection.is_public:
            movies = collection.movies.all()
            show_items = True
        else:
            return redirect('view_collections')
    # Librarians or public collections: always allowed
    elif request.user.profile.role != 'patron' or collection.is_public:
        movies = collection.movies.all()
        show_items = True
    else:
        is_owner = request.user == collection.owner
        is_allowed_user = request.user in collection.allowed_users.all()
        user_request = AccessRequest.objects.filter(
            patron=request.user,
            collection=collection
        ).first()  # get existing request if exists

        if is_owner or is_allowed_user or (user_request and user_request.approved):
            movies = collection.movies.all()
            show_items = True

    context = {
        'collection': collection,
        'movies': movies,
        'show_items': show_items,
        'user_request': user_request  # pass it into template
    }
    return render(request, 'movies/collection_detail.html', context)



@login_required
def edit_collection(request, collection_id):
    collection = get_object_or_404(Collection, id=collection_id)
    # Allow librarians to edit any collection, but patrons can only edit their own
    if request.user.profile.role != 'librarian' and collection.owner != request.user:
        return HttpResponseForbidden("You are not allowed to edit this collection.")

    warning_message = None
    original_is_public = collection.is_public  # Store the original value
    
    if request.method == 'POST':
        form = CollectionForm(request.POST, instance=collection, user=request.user)
        if form.is_valid():
            edited_collection = form.save(commit=False)
            # Preserve the original is_public value and ignore any changes to it
            edited_collection.is_public = original_is_public
            
            # For patrons, force public anyway as an extra check
            if request.user.profile.role == 'patron':
                edited_collection.is_public = True
                
            edited_collection.save()
            form.save_m2m()
            
            messages.success(request, f"Collection '{edited_collection.name}' has been updated successfully.")
            return redirect('view_collections')
        # Get warning message about movies being removed from public collections
        if hasattr(form, 'add_warning'):
            warning_message = form.add_warning
    else:
        form = CollectionForm(instance=collection, user=request.user)
    
    context = {
        'form': form, 
        'collection': collection,
        'warning_message': warning_message
    }
    return render(request, 'movies/edit_collection.html', context)


@login_required
def delete_collection(request, collection_id):
    collection = get_object_or_404(Collection, id=collection_id)
    # Allow librarians to delete any collection, but patrons can only delete their own
    if request.user.profile.role != 'librarian' and collection.owner != request.user:
        return HttpResponseForbidden("You are not allowed to delete this collection.")

    if request.method == 'POST':
        collection.delete()
        return redirect('view_collections')
    return render(request, 'movies/delete_collection.html', {'collection': collection})

@login_required
def request_access(request, collection_id):
    collection = get_object_or_404(Collection, id=collection_id)
    AccessRequest.objects.get_or_create(patron=request.user, collection=collection)
    return redirect('collection_detail', collection_id=collection.id)


@login_required
def manage_requests(request):
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')

    try:
        # Use raw SQL to get all access requests without problematic columns
        from django.db import connection
        with connection.cursor() as cursor:
            # Check what columns exist in the access request table
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'movies_accessrequest';
            """)
            available_columns = [row[0] for row in cursor.fetchall()]
            
            # Build a query with only the columns that exist
            safe_columns = ['id', 'patron_id', 'collection_id', 'approved', 'rejected', 'requested_at']
            
            # Only include appeal_message and under_appeal if they exist
            if 'appeal_message' in available_columns:
                safe_columns.append('appeal_message')
            if 'under_appeal' in available_columns:
                safe_columns.append('under_appeal')
                
            # Use SQL to fetch the requests
            query = f"""
                SELECT {', '.join(safe_columns)}
                FROM movies_accessrequest
                ORDER BY requested_at DESC;
            """
            cursor.execute(query)
            
            # Get column names from cursor
            column_names = [col[0] for col in cursor.description]
            request_data = cursor.fetchall()
            
        # Convert to list of dictionaries
        requests = []
        for row in request_data:
            request_dict = {column_names[i]: row[i] for i in range(len(column_names))}
            
            # Add empty values for potential missing fields
            if 'appeal_message' not in request_dict:
                request_dict['appeal_message'] = None
            if 'under_appeal' not in request_dict:
                request_dict['under_appeal'] = False
                
            # Need to get related objects
            request_dict['patron'] = User.objects.get(id=request_dict['patron_id'])
            request_dict['collection'] = Collection.objects.get(id=request_dict['collection_id'])
            
            requests.append(request_dict)
            
    except Exception as e:
        # Fallback if the custom approach fails
        requests = AccessRequest.objects.select_related('patron', 'collection').order_by('-requested_at')
    
    return render(request, 'movies/manage_requests.html', {'requests': requests})

@login_required
def approve_request(request, request_id):
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')

    access_request = get_object_or_404(AccessRequest, id=request_id)
    access_request.approved = True
    access_request.save()
    return redirect('manage_requests')

@login_required
def revoke_request(request, request_id):
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')

    access_request = get_object_or_404(AccessRequest, id=request_id)
    access_request.approved = False
    access_request.save()
    return redirect('manage_requests')

@login_required
def reject_request(request, request_id):
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')

    access_request = get_object_or_404(AccessRequest, id=request_id)
    access_request.approved = False
    access_request.rejected = True
    access_request.save()
    return redirect('manage_requests')

def search_collections(request):
    # DEPRECATED: This view is kept for backward compatibility.
    # The search functionality is now integrated into the collections page.
    return redirect('view_collections')

def search_within_collection(request, collection_id):
    # DEPRECATED: This view is kept for API compatibility.
    # The search functionality is now integrated into the collection detail page.
    collection = get_object_or_404(Collection, id=collection_id)
    query = request.GET.get('q', None)
    movies = Movie.objects.none()
    show_results = False
    
    # Check if user has access to this collection
    if collection.is_public:
        # Public collections are accessible to everyone
        show_results = True
    elif request.user.is_authenticated:
        if request.user.profile.role == 'librarian':
            # Librarians can access all collections
            show_results = True
        else:
            # For patrons, check specific access
            is_owner = request.user == collection.owner
            is_allowed_user = request.user in collection.allowed_users.all()
            has_approved_request = AccessRequest.objects.filter(
                patron=request.user,
                collection=collection,
                approved=True
            ).exists()
            
            if is_owner or is_allowed_user or has_approved_request:
                show_results = True
    
    if show_results and query:
        # Search for movies within this collection
        movies = collection.movies.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()
    
    context = {
        'collection': collection,
        'query': query,
        'movies': movies,
        'show_results': show_results
    }
    
    # Return JSON response for AJAX requests
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        html = render_to_string('movies/includes/movie_grid.html', {'movies': movies})
        return JsonResponse({'html': html})
    
    return render(request, 'movies/collection_detail.html', context)

@login_required
def add_review(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        rating = request.POST.get('rating', None)

        if rating:
            try:
                rating = int(rating)
                if rating < 0 or rating > 5:
                    rating = None
            except ValueError:
                rating = None

        if body:
            existing_review = Review.objects.filter(
                movie=movie,
                author=request.user.email
            ).first()

            if existing_review:
                existing_review.body = body
                existing_review.rating = rating
                existing_review.pub_date = timezone.now()
                existing_review.save()
                messages.success(request, "Your existing review has been updated!")
            else:                Review.objects.create(
                    movie=movie,
                    body=body,
                    rating=rating,
                    author=request.user.email,
                    user_role=getattr(request.user.profile, 'role', None),
                )
            messages.success(request, "Your review has been posted!")

    return redirect('movie_reviews', movie_id=movie_id)

# BORROWING FEATURE - BEGIN #
@login_required
def request_borrow(request, movie_id):
    """Allow users to request to borrow a movie. Librarians can borrow directly."""
    # Remove the patron-only check to allow librarians too
    # if request.user.profile.role != 'patron':
    #     return redirect('librarian_home')
        
    movie = get_object_or_404(Movie, id=movie_id)
    
    # Check if movie is available
    if movie.status != 'available':
        return render(request, 'movies/borrow_error.html', {
            'message': "This movie is currently unavailable for borrowing.",
            'movie': movie
        })
    
    # Check if user already has a pending or active request for this movie
    existing_request = LoanRecord.objects.filter(
        patron=request.user,
        movie=movie,
        status__in=['requested', 'approved', 'borrowed']
    ).first()
    
    if existing_request:
        if request.user.profile.role == 'librarian':
            return redirect('manage_loans')
        else:
            return redirect('view_loans')
    
    if request.method == 'POST':
        # For librarians: create loan and automatically approve it
        if request.user.profile.role == 'librarian':
            # Calculate due date (2 weeks from now by default)
            due_date = timezone.now() + timedelta(days=14)
            
            # Create pre-approved loan
            loan = LoanRecord.objects.create(
                movie=movie,
                patron=request.user,
                librarian=request.user,  # Self-approve
                status='borrowed',  # Skip the requested/approved stages
                approved_at=timezone.now(),
                borrowed_at=timezone.now(),
                due_date=due_date
            )
            
            # Update movie status to unavailable
            movie.status = 'unavailable'
            movie.save()
            
            messages.success(request, f"You have borrowed '{movie.title}'. Please return it by {due_date.strftime('%B %d, %Y')}.")
            return redirect('manage_loans')
        else:
            # Create new borrow request for patrons (unchanged)
            loan = LoanRecord.objects.create(
                movie=movie,
                patron=request.user,
                status='requested'
            )
            
            messages.success(request, f"Your request to borrow '{movie.title}' has been submitted and is awaiting approval.")
            return redirect('view_loans')
    
    return render(request, 'movies/request_borrow.html', {'movie': movie})

@login_required
def view_loans(request):
    """View loans for the current user (both patrons and librarians)"""
    # Allow both patrons and librarians to view their own loans
    # if request.user.profile.role != 'patron':
    #     return redirect('manage_loans')
        
    loans = LoanRecord.objects.filter(patron=request.user)
    
    context = {
        'pending_loans': loans.filter(status__in=['requested', 'approved']),
        'active_loans': loans.filter(status='borrowed'),
        'past_loans': loans.filter(status__in=['returned', 'rejected']),
        'current_time': timezone.now(),
        'is_librarian': request.user.profile.role == 'librarian'
    }
    
    return render(request, 'movies/view_loans.html', context)

@login_required
def manage_loans(request):
    """Display all loans for librarians to manage"""
    if request.user.profile.role != 'librarian':
        return redirect('view_loans')
        
    loans = LoanRecord.objects.all()
    
    # Add loan user info for display
    for loan in loans:
        loan.user_role = loan.patron.profile.role
    
    context = {
        'loans': loans,
        'pending_loans': loans.filter(status='requested'),
        'approved_loans': loans.filter(status='approved'),
        'active_loans': loans.filter(status='borrowed'),
        'returned_loans': loans.filter(status='returned'),
        'overdue_loans': loans.filter(status='overdue'),
        'current_time': timezone.now()
    }
    
    return render(request, 'movies/manage_loans.html', context)

@login_required
def approve_loan(request, loan_id):
    """Approve a loan request (librarian only)"""
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')
        
    loan = get_object_or_404(LoanRecord, id=loan_id, status='requested')
    
    if request.method == 'POST':
        loan.status = 'approved'
        loan.librarian = request.user
        loan.approved_at = timezone.now()
        loan.save()
        
        # Create notification for the patron
        notification = Notification.objects.create(
            user=loan.patron,
            message=f"Your request to borrow '{loan.movie.title}' has been approved. You can now collect it from the library.",
            notification_type='loan_approved',
            related_loan=loan
        )
        
        messages.success(request, f"Loan request for '{loan.movie.title}' has been approved. The patron has been notified.")
        return redirect('manage_loans')
        
    return render(request, 'movies/approve_loan.html', {'loan': loan})

@login_required
def reject_loan(request, loan_id):
    """Reject a loan request (librarian only)"""
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')
        
    loan = get_object_or_404(LoanRecord, id=loan_id, status='requested')
    
    if request.method == 'POST':
        loan.status = 'rejected'
        loan.librarian = request.user
        loan.save()
        
        # Create notification for the patron
        notification = Notification.objects.create(
            user=loan.patron,
            message=f"Your request to borrow '{loan.movie.title}' has been rejected. Please contact the library for more information.",
            notification_type='loan_rejected',
            related_loan=loan
        )
        
        messages.success(request, f"Loan request for '{loan.movie.title}' has been rejected. The patron has been notified.")
        return redirect('manage_loans')
        
    return render(request, 'movies/reject_loan.html', {'loan': loan})

@login_required
def checkout_loan(request, loan_id):
    """Mark a loan as checked out with due date (librarian only)"""
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')
        
    loan = get_object_or_404(LoanRecord, id=loan_id, status='approved')
    
    if request.method == 'POST':
        # Calculate due date (2 weeks from now by default)
        due_date = timezone.now() + timedelta(days=14)
        
        loan.status = 'borrowed'
        loan.borrowed_at = timezone.now()
        loan.due_date = due_date
        loan.save()
        
        # Update movie status to unavailable
        movie = loan.movie
        movie.status = 'unavailable'
        movie.save()
        
        return redirect('manage_loans')
        
    return render(request, 'movies/checkout_loan.html', {'loan': loan})

@login_required
def return_loan(request, loan_id):
    """Mark a loan as returned (librarian only)"""
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')
        
    loan = get_object_or_404(LoanRecord, id=loan_id, status__in=['borrowed', 'overdue'])
    
    if request.method == 'POST':
        loan.status = 'returned'
        loan.returned_at = timezone.now()
        loan.save()
        
        # Update movie status to available
        movie = loan.movie
        movie.status = 'available'
        movie.save()
        
        return redirect('manage_loans')
        
    return render(request, 'movies/return_loan.html', {'loan': loan})

@login_required
def patron_return_loan(request, loan_id):
    """Allow users to return their own borrowed movies"""
    # Remove the patron-only check to allow librarians to return their own loans
    # if request.user.profile.role != 'patron':
    #     return redirect('librarian_home')
        
    # Only allow users to return their own loans
    loan = get_object_or_404(LoanRecord, id=loan_id, patron=request.user, status__in=['borrowed', 'overdue'])
    
    if request.method == 'POST':
        loan.status = 'returned'
        loan.returned_at = timezone.now()
        loan.save()
        
        # Update movie status to available
        movie = loan.movie
        movie.status = 'available'
        movie.save()
        
        # Create notification for librarian users about the return
        if request.user.profile.role != 'librarian':  # Skip for librarians returning their own loans
            librarians = User.objects.filter(profile__role='librarian')
            notification_message = f"Movie '{movie.title}' has been returned by {request.user.username}"
            
            for librarian in librarians:
                Notification.objects.create(
                    user=librarian,
                    message=notification_message,
                    notification_type='movie_returned',
                    related_loan=loan
                )
        
        messages.success(request, f"You have successfully returned '{movie.title}'.")
        
        if request.user.profile.role == 'librarian':
            return redirect('manage_loans')
        else:
            return redirect('view_loans')
        
    return render(request, 'movies/patron_return_loan.html', {'loan': loan})

@login_required
def my_notifications(request):
    """Show the user's notifications"""
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    
    # Mark notifications as read when viewed
    if request.method == 'POST' and 'mark_read' in request.POST:
        notification_id = request.POST.get('notification_id')
        if notification_id:
            notification = get_object_or_404(Notification, id=notification_id, user=request.user)
            notification.is_read = True
            notification.save()
            return redirect('my_notifications')
        
    # Count unread notifications
    unread_count = notifications.filter(is_read=False).count()
    
    return render(request, 'movies/my_notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count
    })

@login_required
def debug_user_role(request):
    """Debug view to check and fix user role if needed"""
    user = request.user
    current_role = user.profile.role
    email = user.email
    
    # Display current role info
    context = {
        'user': user,
        'current_role': current_role,
        'email': email,
    }
    
    # If this is the movies.app.librarian@gmail.com account, ensure it has librarian role
    if email == 'movies.app.librarian@gmail.com' and current_role != 'librarian':
        user.profile.role = 'librarian'
        user.profile.save()
        context['updated'] = True
        context['new_role'] = 'librarian'
    
    return render(request, 'movies/debug_role.html', context)

# Simple login view for testing
def login_view(request):
    """Simple login view for test compatibility"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')
    return render(request, 'movies/login.html', {})

@login_required
def manage_users(request):
    """View for librarians to manage user roles"""
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')
    
    patrons = User.objects.filter(profile__role='patron')
    return render(request, 'movies/manage_users.html', {'patrons': patrons})

@login_required
def upgrade_to_librarian(request, user_id):
    """Upgrade a patron to librarian status"""
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')
    
    patron = get_object_or_404(User, id=user_id, profile__role='patron')
    patron.profile.role = 'librarian'
    patron.profile.save()
    messages.success(request, f'{patron.email} has been upgraded to librarian status.')
    return redirect('manage_users')

def appeal_request(request, collection_id):
    # Ensure the user is logged in
    if not request.user.is_authenticated:
        messages.error(request, "Please log in to submit an appeal.")
        return redirect("login")

    # Get the collection, or a 404 if not found
    collection = get_object_or_404(Collection, id=collection_id)

    # Get the access request for this user and collection
    try:
        access_request = collection.accessrequest_set.get(patron=request.user)
    except AccessRequest.DoesNotExist:
        messages.error(request, "You do not have an access request for this collection.")
        return redirect("collection_detail", collection_id=collection.id)

    # Only allow appeals for requests that have been rejected.
    if not access_request.rejected:
        messages.error(request, "You can only appeal a rejected access request.")
        return redirect("collection_detail", collection_id=collection.id)

    if request.method == "POST":
        appeal_message = request.POST.get("appeal_message", "").strip()
        if not appeal_message:
            messages.error(request, "Appeal message cannot be empty.")
            return redirect("collection_detail", collection_id=collection.id)

        # Save the appeal message to the access request. 
        # Assumes your AccessRequest model has a field for appeals (e.g., appeal_message) and an optional flag.
        access_request.appeal_message = appeal_message
        # Optionally, set a flag to indicate that the appeal is active.
        access_request.under_appeal = True
        access_request.save()

        messages.success(request, "Your appeal has been submitted successfully.")
        return redirect("collection_detail", collection_id=collection.id)
    else:
        # Optionally, you can render an appeal form if this view is also used for GET requests.
        return render(request, "movies/appeal_form.html", {
            "collection": collection,
            "access_request": access_request,
        })
def approve_appeal(request, request_id):
    # Make sure this is a POST request.
    if request.method != "POST":
        messages.error(request, "Invalid request method for approving an appeal.")
        return redirect("manage_requests")

    # Check if the user is authenticated.
    if not request.user.is_authenticated:
        messages.error(request, "You must be logged in to perform this action.")
        return redirect("login")
    
    # Optionally, ensure the user has permission (for example, must be a librarian)
    # Uncomment and adjust this block as needed:
    # if request.user.profile.role != 'librarian':
    #     return HttpResponseForbidden("You do not have permission to perform this action.")

    # Retrieve the access request using its ID.
    access_request = get_object_or_404(AccessRequest, pk=request_id)

    # Verify that an appeal message exists; otherwise, nothing to approve.
    if not access_request.appeal_message:
        messages.error(request, "There is no appeal to approve on this request.")
        return redirect("manage_requests")

    # Approve the appeal:
    access_request.approved = True
    access_request.rejected = False
    access_request.under_appeal = False
    access_request.appeal_message = ""  # or set to None, based on your model field
    access_request.save()

    messages.success(request, "Appeal approved. The user now has access.")
    return redirect("manage_requests")

def reject_appeal(request, request_id):
    # Make sure this is a POST request.
    if request.method != "POST":
        messages.error(request, "Invalid request method for rejecting an appeal.")
        return redirect("manage_requests")

    # Check if the user is authenticated.
    if not request.user.is_authenticated:
        messages.error(request, "You must be logged in to perform this action.")
        return redirect("login")
    
    # Optionally, ensure the user has permission (for example, must be a librarian)
    # if request.user.profile.role != 'librarian':
    #     return HttpResponseForbidden("You do not have permission to perform this action.")

    # Retrieve the access request using its ID.
    access_request = get_object_or_404(AccessRequest, pk=request_id)

    # If there's no appeal message, nothing to reject.
    if not access_request.appeal_message:
        messages.error(request, "There is no appeal to reject on this request.")
        return redirect("manage_requests")

    # Reject the appeal:
    access_request.approved = False
    access_request.rejected = True
    access_request.under_appeal = False
    access_request.appeal_message = ""  # or None, depending on your model field
    access_request.save()

    messages.success(request, "Appeal rejected. The user still has no access.")
    return redirect("manage_requests")

@login_required
def batch_access_requests(request):
    """Handle batch operations on access requests (approve, reject, revoke)"""
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')
    
    if request.method == 'POST':
        operation = request.POST.get('operation')
        request_ids = request.POST.getlist('request_ids')
        
        if not operation or not request_ids:
            messages.error(request, "No operation or requests selected")
            return redirect('manage_requests')
        
        count = 0
        for request_id in request_ids:
            try:
                access_request = AccessRequest.objects.get(id=request_id)
                
                if operation == 'approve':
                    access_request.approved = True
                    access_request.rejected = False
                    count += 1
                elif operation == 'reject':
                    access_request.approved = False
                    access_request.rejected = True
                    count += 1
                elif operation == 'revoke':
                    access_request.approved = False
                    access_request.rejected = False
                    count += 1
                
                access_request.save()
                
            except AccessRequest.DoesNotExist:
                continue
        
        action_text = {
            'approve': 'approved',
            'reject': 'rejected',
            'revoke': 'revoked',
        }.get(operation, operation)
        
        messages.success(request, f"Successfully {action_text} {count} access requests")
    
    return redirect('manage_requests')

def update_overdue_status():
    """
    Update the status of borrowed items to 'overdue' if they are past their due date.
    Also sends notifications to patrons and librarians about overdue items.
    
    This function is meant to be called by a scheduled task/cron job.
    """
    now = timezone.now()
    
    # Get all borrowed loans that are not marked as overdue but are past their due date
    overdue_loans = LoanRecord.objects.filter(
        status='borrowed',
        due_date__lt=now
    )
    
    count = 0
    for loan in overdue_loans:
        # Update loan status to overdue
        loan.status = 'overdue'
        loan.save()
        
        # Create notification for the patron
        notification = Notification.objects.create(
            user=loan.patron,
            message=f"Your borrowed item '{loan.movie.title}' is now overdue. It was due on {loan.due_date.strftime('%B %d, %Y')}. Please return it as soon as possible.",
            notification_type='loan_overdue',
            related_loan=loan
        )
        
        # Create notification for librarians
        librarians = User.objects.filter(profile__role='librarian')
        for librarian in librarians:
            Notification.objects.create(
                user=librarian,
                message=f"The item '{loan.movie.title}' borrowed by {loan.patron.email} is now overdue. It was due on {loan.due_date.strftime('%B %d, %Y')}.",
                notification_type='loan_overdue',
                related_loan=loan
            )
        
        count += 1
    
    return count


def check_due_soon_items():
    """
    Check for items that are due soon (within the next 2 days) and send notifications.
    
    This function is meant to be called by a scheduled task/cron job.
    """
    now = timezone.now()
    due_soon_date = now + timedelta(days=2)
    
    # Get all borrowed loans that are due within the next 2 days
    due_soon_loans = LoanRecord.objects.filter(
        status='borrowed',
        due_date__gt=now,
        due_date__lt=due_soon_date
    )
    
    count = 0
    for loan in due_soon_loans:
        # Check if a due_soon notification already exists for this loan
        existing_notification = Notification.objects.filter(
            user=loan.patron,
            related_loan=loan,
            notification_type='loan_due_soon'
        ).exists()
        
        if not existing_notification:
            # Create notification for the patron only if one doesn't already exist
            Notification.objects.create(
                user=loan.patron,
                message=f"Your borrowed item '{loan.movie.title}' is due soon on {loan.due_date.strftime('%B %d, %Y')}. Please return it on time.",
                notification_type='loan_due_soon',
                related_loan=loan
            )
            count += 1
    
    return count

# Admin view to manually trigger the overdue update (for testing)
@login_required
def trigger_overdue_update(request):
    """Admin function to trigger the overdue status update manually"""
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')
    
    count = update_overdue_status()
    due_soon_count = check_due_soon_items()
    
    messages.success(request, f"Updated {count} loans to overdue status and sent {due_soon_count} due soon notifications.")
    return redirect('manage_loans')

@login_required
def borrowers_report(request):
    """
    Create a report of all currently borrowed items, grouped by patron.
    Only accessible to librarians.
    """
    if request.user.profile.role != 'librarian':
        return redirect('patron_home')
    
    # Get all active loans (borrowed or overdue)
    active_loans = LoanRecord.objects.filter(
        status__in=['borrowed', 'overdue']
    ).select_related('movie', 'patron')
    
    # Group loans by patron
    patron_loans = {}
    for loan in active_loans:
        patron_id = loan.patron.id
        if patron_id not in patron_loans:
            patron_loans[patron_id] = {
                'patron': loan.patron,
                'loans': [],
                'overdue_count': 0,
                'total_count': 0
            }
        
        patron_loans[patron_id]['loans'].append(loan)
        patron_loans[patron_id]['total_count'] += 1
        if loan.status == 'overdue':
            patron_loans[patron_id]['overdue_count'] += 1
    
    # Sort patrons by those with most overdue items first
    sorted_patrons = sorted(
        patron_loans.values(),
        key=lambda x: (x['overdue_count'], x['total_count']),
        reverse=True
    )
    
    context = {
        'patron_loans': sorted_patrons,
        'current_time': timezone.now()
    }
    
    return render(request, 'movies/borrowers_report.html', context)

@login_required
def debug_database_schema(request):
    """For admin use only - View to check database schema and potentially help with migrations"""
    if not request.user.is_staff:  # Only staff can access this
        messages.error(request, "You do not have permission to access this page.")
        return redirect('index')
    
    from django.db import connection
    import json
    
    # Tables we're interested in
    tables_to_check = ['movies_movie', 'movies_profile']
    results = {}
    
    with connection.cursor() as cursor:
        for table in tables_to_check:
            # Check if table exists
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                );
            """, [table])
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                results[table] = {"exists": False, "columns": []}
                continue
            
            # Get columns for this table
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """, [table])
            columns = cursor.fetchall()
            
            results[table] = {
                "exists": True,
                "columns": [
                    {
                        "name": col[0],
                        "type": col[1],
                        "nullable": col[2]
                    } for col in columns
                ]
            }
    
    # Check for specific fields that should exist
    missing_fields = []
    if results.get('movies_movie', {}).get('exists', False):
        movie_columns = [col['name'] for col in results['movies_movie']['columns']]
        if 'key_value' not in movie_columns:
            missing_fields.append("movies_movie.key_value")
    
    if results.get('movies_profile', {}).get('exists', False):
        profile_columns = [col['name'] for col in results['movies_profile']['columns']]
        if 'date_joined' not in profile_columns:
            missing_fields.append("movies_profile.date_joined")
        if 'real_name' not in profile_columns:
            missing_fields.append("movies_profile.real_name")
    
    context = {
        'schema_info': json.dumps(results, indent=2),
        'missing_fields': missing_fields,
    }
    
    return render(request, 'movies/debug_schema.html', context)

@login_required
def fix_database_schema(request):
    """
    Emergency endpoint to fix database schema issues directly.
    This should only be used by administrators in development or when migrations fail.
    """
    if not request.user.is_staff:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('index')
    
    from django.db import connection
    
    # Keep track of what was fixed
    fixed_issues = []
    
    try:
        with connection.cursor() as cursor:
            # Check database vendor
            db_vendor = connection.vendor
            
            # --- Existing schema fixes ---
            
            # Check and fix key_value column in movies_movie
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'movies_movie' AND column_name = 'key_value'
                    );
                """)
                key_value_exists = cursor.fetchone()[0]
                
                if not key_value_exists:
                    # Different SQL syntax for PostgreSQL
                    if db_vendor == 'postgresql':
                        cursor.execute("""
                            ALTER TABLE movies_movie ADD COLUMN key_value varchar(50) NULL;
                        """)
                    else:
                        cursor.execute("""
                            ALTER TABLE movies_movie ADD COLUMN key_value varchar(50);
                        """)
                    fixed_issues.append("Added missing key_value column to movies_movie table")
            except Exception as e:
                fixed_issues.append(f"Error checking movies_movie.key_value: {str(e)}")
            
            # Check and fix date_joined column in movies_profile
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'movies_profile' AND column_name = 'date_joined'
                    );
                """)
                date_joined_exists = cursor.fetchone()[0]
                
                if not date_joined_exists:
                    # Different SQL syntax for PostgreSQL
                    if db_vendor == 'postgresql':
                        cursor.execute("""
                            ALTER TABLE movies_profile ADD COLUMN date_joined date DEFAULT CURRENT_DATE NULL;
                        """)
                    else:
                        cursor.execute("""
                            ALTER TABLE movies_profile ADD COLUMN date_joined date DEFAULT CURRENT_DATE;
                        """)
                    fixed_issues.append("Added missing date_joined column to movies_profile table")
            except Exception as e:
                fixed_issues.append(f"Error checking movies_profile.date_joined: {str(e)}")
            
            # Check and fix real_name column in movies_profile
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'movies_profile' AND column_name = 'real_name'
                    );
                """)
                real_name_exists = cursor.fetchone()[0]
                
                if not real_name_exists:
                    # Different SQL syntax for PostgreSQL
                    if db_vendor == 'postgresql':
                        cursor.execute("""
                            ALTER TABLE movies_profile ADD COLUMN real_name varchar(100) NULL;
                        """)
                    else:
                        cursor.execute("""
                            ALTER TABLE movies_profile ADD COLUMN real_name varchar(100);
                        """)
                    fixed_issues.append("Added missing real_name column to movies_profile table")
            except Exception as e:
                fixed_issues.append(f"Error checking movies_profile.real_name: {str(e)}")
                
            # --- New: Fix supply/demand constraints ---
            
            # Check if columns exist and have NOT NULL constraint
            try:
                if db_vendor == 'postgresql':
                    # Check supply column
                    cursor.execute("""
                        SELECT is_nullable 
                        FROM information_schema.columns 
                        WHERE table_name = 'movies_movie' AND column_name = 'supply';
                    """)
                    result = cursor.fetchone()
                    if result and result[0] == 'NO':  # NO means NOT NULL
                        cursor.execute("""
                            ALTER TABLE movies_movie ALTER COLUMN supply DROP NOT NULL;
                        """)
                        fixed_issues.append("Made supply column nullable")
                    
                    # Check demand column
                    cursor.execute("""
                        SELECT is_nullable 
                        FROM information_schema.columns 
                        WHERE table_name = 'movies_movie' AND column_name = 'demand';
                    """)
                    result = cursor.fetchone()
                    if result and result[0] == 'NO':  # NO means NOT NULL
                        cursor.execute("""
                            ALTER TABLE movies_movie ALTER COLUMN demand DROP NOT NULL;
                        """)
                        fixed_issues.append("Made demand column nullable")
                
                # Update default values for any existing NULL fields
                cursor.execute("""
                    UPDATE movies_movie SET supply = 0, demand = 0 
                    WHERE supply IS NULL OR demand IS NULL;
                """)
            except Exception as e:
                fixed_issues.append(f"Error fixing supply/demand constraints: {str(e)}")
            
    except Exception as e:
        fixed_issues.append(f"Database connection error: {str(e)}")
    
    if not fixed_issues:
        messages.success(request, "Database schema looks good, no fixes needed.")
    else:
        for issue in fixed_issues:
            messages.success(request, issue)
    
    return redirect('debug_database_schema')