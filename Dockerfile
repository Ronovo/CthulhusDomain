FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REPO_URL=https://github.com/Ronovo/Dead-But-Dreaming.git \
    BUILD_CMD="pip install --no-cache-dir --user -q -r requirements.txt" \
    DATA_DIR=/app/data

WORKDIR /app

COPY docker/git-sync.sh /usr/local/bin/git-sync
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i 's/\r$//' /usr/local/bin/git-sync && chmod +x /usr/local/bin/git-sync

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

# Game state comes from the browser and accounts are in SQLite, so any number of workers can serve a request.
ENTRYPOINT ["git-sync"]
CMD ["gunicorn", "--chdir", "Game_Logic", "--bind", "0.0.0.0:8000", "--workers", "2", "webapp:create_app()"]
