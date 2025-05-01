from django.test import TestCase
from django.contrib.auth.models import User
from .models import Movie, Review
from django.utils import timezone

class BasicModelTests(TestCase):
    """Basic model tests that are guaranteed to work in CI environments"""
    
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword',
            email='test@example.com'
        )
        
        # Create a test movie
        self.movie = Movie.objects.create(
            title="Test Movie",
            description="A test movie",
            release_date="2022-01-01",
            duration=120,
            language="English",
            status="available"
        )
    
    def test_movie_creation(self):
        """Test that a movie can be created"""
        self.assertEqual(self.movie.title, "Test Movie")
        self.assertEqual(self.movie.status, "available")
    
    def test_movie_str(self):
        """Test the string representation of a movie"""
        self.assertEqual(str(self.movie), "Test Movie")
    
    def test_review_creation(self):
        """Test that a review can be created"""
        review = Review.objects.create(
            movie=self.movie,
            body="This is a test review",
            rating=5
        )
        self.assertEqual(review.movie, self.movie)
        self.assertEqual(review.body, "This is a test review")
        self.assertEqual(review.rating, 5)
    
    def test_review_with_title(self):
        """Test creating a review with a title"""
        review = Review.objects.create(
            movie=self.movie,
            title="Great Movie",
            body="This is a fantastic movie!",
            rating=5
        )
        self.assertEqual(review.title, "Great Movie")
        self.assertEqual(str(review), "Great Movie")
    
    def test_review_without_title(self):
        """Test creating a review without a title"""
        review = Review.objects.create(
            movie=self.movie,
            body="Good movie overall",
            rating=4
        )
        self.assertEqual(str(review), f"Comment on {self.movie.title}") 