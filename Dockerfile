# Plan 35 — asset-finance-modeler Docker image
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    PORT=8015

WORKDIR /app

# Build deps for numpy/scipy/faiss
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system .

COPY src ./src

RUN mkdir -p /data/scenarios
VOLUME /data/scenarios

EXPOSE 8015
CMD ["asset-finance-modeler-http"]
