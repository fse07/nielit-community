# ─────────────────────────────────────────────────────────────
# Nielit Community — container image
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Minimal runtime OS packages. psycopg2-binary and Pillow both
# ship manylinux wheels so no build toolchain is needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps layer (cache-friendly: only re-runs when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Create unprivileged runtime user, set up upload dirs, mark entrypoint executable
RUN useradd --create-home --shell /bin/bash --uid 1000 nielit \
    && mkdir -p /app/app/static/uploads/images \
                /app/app/static/uploads/videos \
                /app/app/static/uploads/avatars \
                /app/app/static/uploads/covers \
    && chown -R nielit:nielit /app \
    && chmod +x /app/docker-entrypoint.sh

USER nielit

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=wsgi.py \
    UPLOAD_FOLDER=/app/app/static/uploads

EXPOSE 8000

# tini reaps zombies and forwards signals cleanly to gunicorn
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]

CMD ["gunicorn", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--bind", "0.0.0.0:8000", \
     "wsgi:application"]
