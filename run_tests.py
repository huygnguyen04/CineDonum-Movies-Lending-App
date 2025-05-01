#!/usr/bin/env python3
"""
Helper script to run tests with the correct PostgreSQL settings.
Usage: python run_tests.py [test_path]
Example: python run_tests.py movies.tests.ReviewModelTest
"""

import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    # Set up the testing environment
    os.environ["DJANGO_SETTINGS_MODULE"] = "mysite.settings"
    django.setup()
    
    # Get the test runner
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=True)
    
    # Run the tests
    test_label = sys.argv[1] if len(sys.argv) > 1 else "movies"
    failures = test_runner.run_tests([test_label])
    
    # Exit with appropriate code
    sys.exit(bool(failures)) 