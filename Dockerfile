FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REPO_URL=https://github.com/Ronovo/Dead-But-Dreaming.git \
    BUILD_CMD="pip install --no-cache-dir --user -q -r requirements.txt" \
    DATA_DIR=/app/data

WORKDIR /app

COPY docker/git-sync.sh /usr/local/bin/git-sync
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && chmod +x /usr/local/bin/git-sync

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0 \
    && useradd --create-home --uid 1000 dreamer \
    && mkdir -p /app/data \
    && chown -R dreamer /app

COPY --chown=dreamer . .
USER dreamer

# Accounts and the generated session key live in /app/data.
VOLUME ["/app/data"]
EXPOSE 8000

# Threaded workers keep each browser's connection open between its updates, four times a second.
ENTRYPOINT ["git-sync"]
CMD ["gunicorn", "--chdir", "Game_Logic", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--keep-alive", "5", "--preload", "webapp:create_app()"]
