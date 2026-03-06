FROM python:3.10.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD sh -c "\
echo '>>> migrate' && \
python manage.py migrate --noinput && \
echo '>>> collectstatic' && \
python manage.py collectstatic --noinput && \
echo '>>> load fixture if needed' && \
if [ \"${LOAD_FIXTURE:-0}\" = \"1\" ]; then \
  python manage.py load_data_safe --fixture data_dump.json; \
fi && \
echo '>>> starting gunicorn' && \
gunicorn InventoryMS.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers 2 \
  --timeout 300 \
  --log-level info
"