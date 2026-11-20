# Stage 1: Build dependencies
FROM python:3.11-slim as builder

WORKDIR /build

# Install build tools if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Minimal runtime image
FROM python:3.11-slim as runtime

WORKDIR /app

# Ensure curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python dependencies from builder
COPY --from=builder /install /usr/local

# Create data directory for SQLite volume persistence
RUN mkdir -p /data && chmod 777 /data

# Copy application source code
COPY app /app/app
COPY tests /app/tests
COPY pyproject.toml /app/pyproject.toml

ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL="sqlite:////data/app.db"
ENV PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
