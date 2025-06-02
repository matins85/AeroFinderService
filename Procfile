release: python3 manage.py migrate

# Using Gunicorn for HTTP
web: gunicorn aerofinder.wsgi --preload --log-file - --log-level debug