# The coverage reports only show what the tests reach, so failing tests or low coverage still build the image.
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS python-coverage
WORKDIR /src
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
RUN python -m coverage run -m pytest -p no:cacheprovider ; \
    python -m coverage html --fail-under=0 ; mkdir -p coverage/python ; \
    python -m coverage json --fail-under=0 -o coverage.json ; \
    python coverage-index/tools/functions.py coverage.json coverage/python/functions.json

FROM node:24-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS js-coverage
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx vitest run --coverage ; mkdir -p coverage/js ; cat coverage-index/istanbul.css >> coverage/js/base.css

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

COPY --chown=dreamer Game_Logic Game_Logic
COPY --chown=dreamer coverage-index/index.html coverage/
COPY --chown=dreamer coverage-reports.json coverage/reports.json
COPY --chown=dreamer --from=python-coverage /src/coverage/python coverage/python
COPY --chown=dreamer --from=js-coverage /src/coverage/js coverage/js
USER dreamer

# Accounts and the generated session key live in /app/data.
VOLUME ["/app/data"]
EXPOSE 8000

# Threaded workers keep each browser's connection open between its updates, four times a second.
ENTRYPOINT ["git-sync"]
CMD ["gunicorn", "--chdir", "Game_Logic", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--keep-alive", "5", "--preload", "webapp:create_app()"]
