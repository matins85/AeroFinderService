release: python manage.py migrate
web: daphne aerofinder.asgi:application --port $PORT --bind 0.0.0.0 -v2
# web: gunicorn RentAnythingServer.wsgi --preload --log-file - --log-level debug
# worker: python manage.py runworker channel_layer
