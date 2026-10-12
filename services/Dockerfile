FROM python:3.12-slim
WORKDIR /app

# Install system dependencies required by psycopg2 / cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy the uv project and local dependency source before syncing the locked
# runtime dependency set. The API is executed from source, not installed as a
# wheel, so the flat setuptools package list is not used by this image.
COPY services/api/pyproject.toml services/api/uv.lock /app/services/api/
COPY services/api /app/services/api
COPY packages/shared /app/packages/shared
RUN cd /app/services/api && uv sync --locked --no-dev

# Copy every repository-root runtime package imported by the API/reporting
# routes. Keep this layout so imports resolve as services.* and data.* from
# the repository root without host-specific paths or development mounts.
COPY services/__init__.py /app/services/__init__.py
COPY services/reporting /app/services/reporting
COPY services/telemetry /app/telemetry
COPY data/__init__.py /app/data/__init__.py
COPY data/pipelines /app/data/pipelines

WORKDIR /app/services/api

ENV PATH="/app/services/api/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

EXPOSE 8000
CMD ["/app/services/api/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]