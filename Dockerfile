# asset-finance-modeler — imagen del Simulador Financiero (API + SPA)
# Multi-stage: (1) build de la SPA React, (2) servicio Python (FastAPI) que sirve API + SPA.

# --- Stage 1: build del frontend ---
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build          # genera /web/dist

# --- Stage 2: servicio Python ---
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    PORT=8015 \
    SIM_WEB_DIST=/app/web/dist

WORKDIR /app

# Build deps para numpy/scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system .

# Copiar la SPA construida; FastAPI la sirve desde SIM_WEB_DIST
COPY --from=web /web/dist /app/web/dist

RUN mkdir -p /data/scenarios
VOLUME /data/scenarios

EXPOSE 8015
# SIM_TOKEN se inyecta en runtime (-e SIM_TOKEN=...) para proteger el enlace
CMD ["asset-finance-modeler-http"]
