FROM python:3.10.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# run migrations when container starts
CMD python manage.py migrate --noinput && \
    gunicorn InventoryMS.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120