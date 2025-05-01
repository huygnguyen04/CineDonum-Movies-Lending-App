from django.db import migrations, connection


def alter_supply_demand_constraints(apps, schema_editor):
    """Make supply and demand fields nullable in PostgreSQL"""
    
    # Skip for SQLite - these fields don't have constraints
    if connection.vendor == 'sqlite':
        # For SQLite, we need to make sure the columns exist
        with connection.cursor() as cursor:
            # Check if the supply and demand columns exist with the right constraints
            cursor.execute("PRAGMA table_info(movies_movie);")
            columns = {col[1]: col for col in cursor.fetchall()}
            
            # If columns don't exist or have NOT NULL constraint, modify them
            if 'supply' not in columns:
                cursor.execute("ALTER TABLE movies_movie ADD COLUMN supply INTEGER NULL;")
            elif columns['supply'][3] == 1:  # Has NOT NULL constraint
                # For SQLite, we'd need to recreate the table to modify constraints
                # This is complex, so we'll just add the column if missing
                print("SQLite doesn't easily support dropping NOT NULL constraints - skipping")
                
            if 'demand' not in columns:
                cursor.execute("ALTER TABLE movies_movie ADD COLUMN demand INTEGER NULL;")
            elif columns['demand'][3] == 1:  # Has NOT NULL constraint
                print("SQLite doesn't easily support dropping NOT NULL constraints - skipping")
    else:
        # PostgreSQL approach
        try:
            with connection.cursor() as cursor:
                # Check if the columns exist and have NOT NULL constraints
                cursor.execute("""
                    SELECT column_name, is_nullable 
                    FROM information_schema.columns 
                    WHERE table_name = 'movies_movie' 
                    AND column_name IN ('supply', 'demand')
                    AND is_nullable = 'NO';
                """)
                columns_to_alter = cursor.fetchall()
                
                if columns_to_alter:
                    cursor.execute("""
                        ALTER TABLE movies_movie 
                        ALTER COLUMN supply DROP NOT NULL,
                        ALTER COLUMN demand DROP NOT NULL;
                    """)
        except Exception as e:
            print(f"Error in PostgreSQL supply/demand constraints: {str(e)}")
            # For ORM fallback, we can't easily modify constraints
            # Let's make sure the fields exist at least
            try:
                Movie = apps.get_model('movies', 'Movie')
                for field_name in ['supply', 'demand']:
                    try:
                        Movie._meta.get_field(field_name)
                    except:
                        # Add field if missing
                        from django.db import models
                        field = models.IntegerField(null=True, blank=True)
                        field.contribute_to_class(Movie, field_name)
            except Exception as e2:
                print(f"Error in fallback constraint migration: {str(e2)}")


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0021_fix_movie_key_value'),
    ]

    operations = [
        migrations.RunPython(alter_supply_demand_constraints, migrations.RunPython.noop),
    ] 