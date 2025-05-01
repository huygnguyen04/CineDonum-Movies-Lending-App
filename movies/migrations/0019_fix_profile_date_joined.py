from django.db import migrations, models, connection, DatabaseError
import django.utils.timezone


def add_profile_fields(apps, schema_editor):
    """Add date_joined and real_name fields to Profile if they don't exist"""
    
    # First, check if we're using SQLite
    if connection.vendor == 'sqlite':
        # For SQLite, check if the columns exist in the table schema
        with connection.cursor() as cursor:
            # Get table info for the profile table
            cursor.execute("PRAGMA table_info(movies_profile);")
            columns = [col[1] for col in cursor.fetchall()]
            
            # If columns don't exist, add them through Django ORM
            if 'date_joined' not in columns or 'real_name' not in columns:
                # Get the Profile model
                Profile = apps.get_model('movies', 'Profile')
                
                # Add fields if they're missing
                try:
                    from django.db import models
                    from django.db.models import DateField, CharField
                    
                    if 'date_joined' not in columns:
                        # Add the field to the model
                        field = DateField(null=True, blank=True, auto_now_add=True)
                        field.contribute_to_class(Profile, 'date_joined')
                        
                    if 'real_name' not in columns:
                        # Add the field to the model
                        field = CharField(max_length=100, null=True, blank=True)
                        field.contribute_to_class(Profile, 'real_name')
                        
                except Exception as e:
                    print(f"Error adding SQLite fields: {str(e)}")
    else:
        # For PostgreSQL, try direct SQL approach
        try:
            with connection.cursor() as cursor:
                # Check if date_joined column exists
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'movies_profile' AND column_name = 'date_joined';
                """)
                if not cursor.fetchone():
                    # Add the column if it doesn't exist
                    cursor.execute("ALTER TABLE movies_profile ADD COLUMN date_joined date DEFAULT CURRENT_DATE;")
                
                # Check if real_name column exists
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'movies_profile' AND column_name = 'real_name';
                """)
                if not cursor.fetchone():
                    # Add the column if it doesn't exist
                    cursor.execute("ALTER TABLE movies_profile ADD COLUMN real_name varchar(100) NULL;")
        except Exception as e:
            print(f"Error in PostgreSQL migration: {str(e)}")
            # Fallback to ORM approach if direct SQL fails
            try:
                Profile = apps.get_model('movies', 'Profile')
                # We can't check column existence without raw SQL, so just try to update the model
                from django.db import models
                from django.db.models import DateField, CharField
                
                try:
                    field = DateField(null=True, blank=True, auto_now_add=True)
                    field.contribute_to_class(Profile, 'date_joined')
                except:
                    pass
                    
                try:
                    field = CharField(max_length=100, null=True, blank=True)
                    field.contribute_to_class(Profile, 'real_name')
                except:
                    pass
            except Exception as e2:
                print(f"Error in fallback migration: {str(e2)}")


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_profile_fields, migrations.RunPython.noop),
    ] 