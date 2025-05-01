from django.urls import path, include
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.index, name='index'),
    path('rolepick/', views.rolepick, name='rolepick'),
    path('patron_home/', views.patron_view, name='patron_home'),
    path('librarian_home/', views.librarian_view, name='librarian_home'),
    path('guest_home/', views.guest_view, name='guest_home'),
    path("logout/", views.logout_view, name='logout'),  # Ensure this matches the view name
    path('search/', views.search_movies, name='search_movies'),
    path('search_collections/', views.search_collections, name='search_collections'),
    path('collections/<int:collection_id>/search/', views.search_within_collection, name='search_within_collection'),
    path('available_movies/', views.available_movies, name='available_movies'),
    path("accounts/", include("allauth.urls")),
    path('<int:movie_id>/reviews/',    views.movie_reviews, name='movie_reviews'),
    path('<int:movie_id>/add_review/',    views.add_review,    name='add_review'),
    path('upload_profile_picture/', views.upload_profile_picture, name='upload_profile_picture'),
    path('movies/add_movie/', views.add_movie, name='add_movie'),  # if adding new movies
    path('movies/remove_image/<int:image_id>/', views.remove_movie_image, name='remove_movie_image'),
    path('movies/remove/<int:movie_id>/', views.remove_movie, name='remove_movie'),
    path('movies/<int:movie_id>/add_image/', views.add_movie_image, name='add_movie_image'),
    path('add_collection/', views.add_collection, name='add_collection'),
    path('collections/', views.view_collections, name='view_collections'),
    path('collections/<int:collection_id>/', views.collection_detail, name='collection_detail'),
    path('collections/<int:collection_id>/edit/', views.edit_collection, name='edit_collection'),
    path('collections/<int:collection_id>/delete/', views.delete_collection, name='delete_collection'),
    ##Collection access
    path('collections/<int:collection_id>/request-access/', views.request_access, name='request_access'),
    path('manage-requests/', views.manage_requests, name='manage_requests'),
    path('approve-request/<int:request_id>/', views.approve_request, name='approve_request'),
    path('revoke-request/<int:request_id>/', views.revoke_request, name='revoke_request'),
    path('reject-request/<int:request_id>/', views.reject_request, name='reject_request'),
    ##appeal
    path('appeal-request/<int:collection_id>/', views.appeal_request, name='appeal_request'),
    path('approve-appeal/<int:request_id>/', views.approve_appeal, name='approve_appeal'),
    path('reject-appeal/<int:request_id>/', views.reject_appeal, name='reject_appeal'),


    
    # Borrowing feature URLs
    path('movies/<int:movie_id>/borrow/', views.request_borrow, name='request_borrow'),
    path('loans/', views.view_loans, name='view_loans'),
    path('manage-loans/', views.manage_loans, name='manage_loans'),
    path('loans/<int:loan_id>/approve/', views.approve_loan, name='approve_loan'),
    path('loans/<int:loan_id>/reject/', views.reject_loan, name='reject_loan'),
    path('loans/<int:loan_id>/checkout/', views.checkout_loan, name='checkout_loan'),
    path('loans/<int:loan_id>/return/', views.return_loan, name='return_loan'),
    path('loans/<int:loan_id>/patron-return/', views.patron_return_loan, name='patron_return_loan'),
    
    # Authentication URLs (add login for tests)
    path('login/', views.login_view, name='login'),
    path('patron_return_loan/<int:loan_id>/', views.patron_return_loan, name='patron_return_loan'),
    path('manage_users/', views.manage_users, name='manage_users'),
    path('upgrade_to_librarian/<int:user_id>/', views.upgrade_to_librarian, name='upgrade_to_librarian'),
    # Debug URL for checking and fixing user roles
    path('debug-role/', views.debug_user_role, name='debug_role'),
    # Debug and maintenance tools - staff only
    path('admin/debug/schema/', views.debug_database_schema, name='debug_database_schema'),
    path('admin/debug/fix-schema/', views.fix_database_schema, name='fix_database_schema'),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)