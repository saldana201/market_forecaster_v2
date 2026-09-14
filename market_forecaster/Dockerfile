# Market Forecaster — Production Dockerfile
# Runs both Streamlit (port 8501) and FastAPI (port 8000)

FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Expose both ports
EXPOSE 8000 8501

# Default: run FastAPI (override with docker-compose for Streamlit)
CMD ["uvicorn", "market_forecaster.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
