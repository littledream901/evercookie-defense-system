# syntax=docker/dockerfile:1.6
# Worker 生产镜像
ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl \
 && rm -rf /var/lib/apt/lists/*

COPY shared /build/shared
COPY worker /build/worker

RUN pip install --upgrade pip \
 && pip install --prefix=/install ./shared \
 && pip install --prefix=/install ./worker

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app WORKER_HEALTH_PORT=9091

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 1000 --home /app fangyu

WORKDIR /app
COPY --from=builder /install /usr/local
COPY worker/src /app/src

USER fangyu
EXPOSE 9091

HEALTHCHECK --interval=15s --timeout=3s --retries=5 --start-period=15s \
  CMD curl -fsS http://127.0.0.1:${WORKER_HEALTH_PORT}/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "src.entrypoints.main"]
