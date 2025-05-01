from django.contrib import admin
from .models import Movie, Actor, Director, Profile, Review, Genre, MovieImage, Collection, Tag, AccessRequest

# Register your models here.
@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'key_value', 'location', 'status', 'release_date', 'upload_date')
    list_filter = ('status', 'release_date')
    search_fields = ('title', 'description', 'key_value', 'location')
    date_hierarchy = 'upload_date'

class ActorAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name', 'bio')
admin.site.register(Actor, ActorAdmin)

class DirectorAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name', 'bio')
admin.site.register(Director, DirectorAdmin)

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email')
admin.site.register(Profile, ProfileAdmin)

class ReviewAdmin(admin.ModelAdmin):
    list_display = ('title', 'movie', 'rating', 'pub_date')
    list_filter = ('rating', 'pub_date')
    search_fields = ('title', 'body', 'movie__title')
admin.site.register(Review, ReviewAdmin)

class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
admin.site.register(Genre, GenreAdmin)

class MovieImageAdmin(admin.ModelAdmin):
    list_display = ('movie', 'image')
    list_filter = ('movie',)
admin.site.register(MovieImage, MovieImageAdmin)

class CollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'is_public', 'create_date', 'update_date')
    list_filter = ('is_public', 'create_date')
    search_fields = ('name', 'description')
    filter_horizontal = ('movies', 'tags', 'allowed_users')
admin.site.register(Collection, CollectionAdmin)

class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
admin.site.register(Tag, TagAdmin)

class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ('patron', 'collection', 'approved', 'rejected', 'requested_at')
    list_filter = ('approved', 'rejected', 'requested_at')
    search_fields = ('patron__username', 'collection__name')
admin.site.register(AccessRequest, AccessRequestAdmin)