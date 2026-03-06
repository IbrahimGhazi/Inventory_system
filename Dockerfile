FROM python:3.10.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && python manage.py flush --no-input && python manage.py loaddata data_dump.json && gunicorn InventoryMS.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120"]