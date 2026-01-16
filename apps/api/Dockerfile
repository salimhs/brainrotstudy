FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared module first
COPY shared/ /app/shared/

# Copy API requirements and install
COPY apps/api/requirements.txt /app/apps/api/
RUN pip install --no-cache-dir -r /app/apps/api/requirements.txt

# Copy API code
COPY apps/api/ /app/apps/api/

WORKDIR /app/apps/api

# Set Python to run in unbuffered mode for better logging
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
