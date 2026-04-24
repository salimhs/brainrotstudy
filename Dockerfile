# syntax=docker/dockerfile:1.7

# ─── Web builder ─────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS web
WORKDIR /src
COPY web/package.json web/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm npm ci --prefer-offline --no-audit || npm install
COPY web ./
ENV NEXT_PUBLIC_API_BASE=/api
RUN npm run build

# ─── Runtime ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node so we can run Next.js standalone server alongside Python
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (install from pyproject for reproducibility)
COPY server/pyproject.toml /app/server/pyproject.toml
COPY server/brainrotstudy /app/server/brainrotstudy
RUN pip install --no-cache-dir /app/server

# Web runtime from builder
COPY --from=web /src/.next/standalone /app/web
COPY --from=web /src/.next/static /app/web/.next/static
COPY --from=web /src/public /app/web/public

ENV STORAGE_ROOT=/app/storage \
    DB_PATH=/app/storage/brainrotstudy.db \
    NEXT_PUBLIC_API_BASE=/api \
    PORT=8000 \
    HOST=0.0.0.0

EXPOSE 3000 8000

COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
