web: python manage.py migrate --noinput && gunicorn InventoryMS.wsgi:application --bind 0.0.0.0:$PORT --workers 2
