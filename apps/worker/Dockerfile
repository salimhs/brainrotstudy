FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy shared module first
COPY shared/ /app/shared/

# Copy worker requirements and install
COPY apps/worker/requirements.txt /app/apps/worker/
RUN pip install --no-cache-dir -r /app/apps/worker/requirements.txt

# Copy worker code
COPY apps/worker/ /app/apps/worker/

# Copy static assets
COPY assets/ /app/assets/

WORKDIR /app/apps/worker

CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=2"]
