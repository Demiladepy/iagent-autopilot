FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY sentinel ./sentinel
RUN pip install --no-cache-dir -e .

ENV SENTINEL_DB_PATH=/data/sentinel.db
ENV SIMULATOR_MODE=true
ENV SENTINEL_ENV=production
ENV REQUIRE_API_KEY=true

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD [
  "uvicorn",
  "sentinel.main:app",
  "--host", "0.0.0.0",
  "--port", "8000",
  "--proxy-headers",
  "--forwarded-allow-ips", "*"
]
