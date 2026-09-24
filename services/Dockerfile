FROM python:3.12-slim
WORKDIR /app

# Install system dependencies required by psycopg2 / cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency manifests
COPY services/api/requirements.txt /app/services/api/requirements.txt
COPY packages/shared /app/packages/shared

# Install third-party dependencies using uv
RUN uv pip install --system -r /app/services/api/requirements.txt

# Install trackflow-shared as editable local dependency using uv
RUN uv pip install --system -e /app/packages/shared

# Copy API application code
COPY services/api /app/services/api

WORKDIR /app/services/api

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]