from django.test.runner import DiscoverRunner
from django.db import connections
import os


class NoCreateTestDatabaseRouter:
    """Database router that prevents Django from creating a new test database."""
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Allow migrations on all databases
        return True
    
    def allow_relation(self, obj1, obj2, **hints):
        # Allow all relations
        return True
    
    def db_for_read(self, model, **hints):
        # Use default database for reading
        return 'default'
    
    def db_for_write(self, model, **hints):
        # Use default database for writing
        return 'default'


class DatabaseAwareTestRunner(DiscoverRunner):
    """
    A test runner that works with both SQLite (for CI/CD) and PostgreSQL (for local testing)
    """
    
    def setup_databases(self, **kwargs):
        # Use a prefix for all tables created during tests
        self.keepdb = True  # Prevent database creation
        
        # Get test databases from parent class
        test_databases = super().setup_databases(**kwargs)
        
        # For each database connection, check if we need special setup
        for alias in connections:
            connection = connections[alias]
            
            # If PostgreSQL, try to add any missing columns
            if connection.vendor == 'postgresql':
                try:
                    with connection.cursor() as cursor:
                        # Create a test schema to isolate test data
                        cursor.execute("CREATE SCHEMA IF NOT EXISTS test_schema;")
                        cursor.execute("SET search_path TO test_schema, public;")
                        
                        # Get a list of all app tables we need
                        cursor.execute("""
                            SELECT table_name FROM information_schema.tables 
                            WHERE table_schema = 'public' AND table_name LIKE 'movies_%';
                        """)
                        tables = [row[0] for row in cursor.fetchall()]
                        
                        # Create copies of all tables in test schema
                        for table in tables:
                            cursor.execute(f"""
                                CREATE TABLE IF NOT EXISTS test_schema.{table} (
                                    LIKE public.{table} INCLUDING ALL
                                );
                            """)
                        
                        # Check for supply and demand columns
                        cursor.execute("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_schema = 'test_schema' AND table_name = 'movies_movie' 
                            AND column_name IN ('supply', 'demand');
                        """)
                        columns = cursor.fetchall()
                        column_names = [col[0] for col in columns]
                        
                        # Add missing columns if needed
                        if 'supply' not in column_names:
                            cursor.execute("ALTER TABLE test_schema.movies_movie ADD COLUMN supply integer NULL;")
                        if 'demand' not in column_names:
                            cursor.execute("ALTER TABLE test_schema.movies_movie ADD COLUMN demand integer NULL;")
                except Exception as e:
                    print(f"Error setting up PostgreSQL test database: {str(e)}")
        
        return test_databases
    
    def teardown_databases(self, old_config, **kwargs):
        # Clean up the test schema in PostgreSQL
        for alias in connections:
            connection = connections[alias]
            if connection.vendor == 'postgresql':
                try:
                    with connection.cursor() as cursor:
                        # Drop the test schema
                        cursor.execute("DROP SCHEMA IF EXISTS test_schema CASCADE;")
                        cursor.execute("SET search_path TO public;")
                except Exception as e:
                    print(f"Error tearing down PostgreSQL test schema: {str(e)}")
        
        # Call parent teardown
        super().teardown_databases(old_config, **kwargs) 