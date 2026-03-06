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

# ── How to use ────────────────────────────────────────────────────────────────
# FIRST deploy:  set Railway variable  LOAD_FIXTURE=1
#   → runs: migrate → load_data_safe → gunicorn
#
# After data loads: remove LOAD_FIXTURE (or set to 0)
#   → runs: migrate → gunicorn  (fast normal boot)
# ─────────────────────────────────────────────────────────────────────────────
CMD sh -c "\
  echo '>>> migrate' && \
  python manage.py migrate --noinput && \
  if [ \"$LOAD_FIXTURE\" = '1' ]; then \
    echo '>>> load_data_safe' && \
    python manage.py load_data_safe --fixture data_dump.json && \
    echo '>>> fixture done — set LOAD_FIXTURE=0 in Railway to skip next time'; \
  else \
    echo '>>> skipping fixture load'; \
  fi && \
  echo '>>> starting gunicorn' && \
  gunicorn InventoryMS.wsgi \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 300 \
    --log-level info \
"