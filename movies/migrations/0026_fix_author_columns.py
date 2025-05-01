# movies/migrations/0026_fix_author_columns.py
from django.db import migrations, models, connection

def check_columns_exist(apps, schema_editor):
    """Check if columns already exist and only add them if they don't"""
    # Skip for PostgreSQL - handle through operations
    if connection.vendor == 'postgresql':
        return
        
    # For SQLite, we need to check if columns exist
    with connection.cursor() as cursor:
        # Get table info
        cursor.execute("PRAGMA table_info(movies_review);")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Get the Review model
        Review = apps.get_model('movies', 'Review')
        
        # If author doesn't exist, add it
        if 'author' not in columns:
            field = models.CharField(max_length=100, null=True)
            field.contribute_to_class(Review, 'author')
            
        # If user_role doesn't exist, add it
        if 'user_role' not in columns:
            field = models.CharField(max_length=20, null=True)
            field.contribute_to_class(Review, 'user_role')

class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0025_add_appeal_fields'),
    ]

    operations = [
        # First check if columns exist in SQLite
        migrations.RunPython(check_columns_exist, migrations.RunPython.noop),
        
        # Only for PostgreSQL, add columns if they don't exist
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='review',
                    name='author',
                    field=models.CharField(max_length=100, null=True),
                ),
                migrations.AddField(
                    model_name='review',
                    name='user_role',
                    field=models.CharField(max_length=20, null=True),
                ),
            ]
        ),
    ]
