from django.db import migrations, models, connection


def add_key_value_column(apps, schema_editor):
    """Add key_value field to Movie model if it doesn't exist"""
    
    # First, check if we're using SQLite
    if connection.vendor == 'sqlite':
        # For SQLite, check if the column exists in the table schema
        with connection.cursor() as cursor:
            # Get table info for the movies table
            cursor.execute("PRAGMA table_info(movies_movie);")
            columns = [col[1] for col in cursor.fetchall()]
            
            # If column doesn't exist, add it through Django ORM
            if 'key_value' not in columns:
                # Get the Movie model
                Movie = apps.get_model('movies', 'Movie')
                
                # Add field if it's missing
                try:
                    from django.db import models
                    from django.db.models import CharField
                    
                    # Add the field to the model
                    field = CharField(max_length=50, null=True, blank=True)
                    field.contribute_to_class(Movie, 'key_value')
                except Exception as e:
                    print(f"Error adding SQLite key_value field: {str(e)}")
    else:
        # For PostgreSQL, try direct SQL approach
        try:
            with connection.cursor() as cursor:
                # Check if key_value column exists
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'movies_movie' AND column_name = 'key_value';
                """)
                if not cursor.fetchone():
                    # Add the column if it doesn't exist
                    cursor.execute("ALTER TABLE movies_movie ADD COLUMN key_value varchar(50) NULL;")
        except Exception as e:
            print(f"Error in PostgreSQL migration: {str(e)}")
            # Fallback to ORM approach if direct SQL fails
            try:
                Movie = apps.get_model('movies', 'Movie')
                # We can't check column existence without raw SQL, so just try to update the model
                from django.db import models
                from django.db.models import CharField
                
                try:
                    field = CharField(max_length=50, null=True, blank=True)
                    field.contribute_to_class(Movie, 'key_value')
                except:
                    pass
            except Exception as e2:
                print(f"Error in fallback migration: {str(e2)}")


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0020_alter_profile_date_joined'),
    ]

    operations = [
        migrations.RunPython(add_key_value_column, migrations.RunPython.noop),
    ] 