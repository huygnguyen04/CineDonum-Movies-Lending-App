release: python manage.py migrate --noinput
web: gunicorn mysite.wsgi --log-file - --timeout 60 --preload