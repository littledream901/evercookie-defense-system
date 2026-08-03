# syntax=docker/dockerfile:1.6
# Admin API 生产镜像
ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc default-libmysqlclient-dev pkg-config curl \
 && rm -rf /var/lib/apt/lists/*

COPY shared /build/shared
COPY admin-api /build/admin-api

RUN pip install --upgrade pip \
 && pip install --prefix=/install ./shared \
 && pip install --prefix=/install ./admin-api

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app ADMIN_PORT=8081

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl tini default-libmysqlclient-dev \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 1000 --home /app fangyu

WORKDIR /app
COPY --from=builder /install /usr/local
COPY admin-api/src /app/src

# 迁移脚本随镜像发布：容器内执行 `alembic upgrade head` 是生产的标准迁移入口，
# 缺了这两项会导致部署时无法建表。
COPY admin-api/alembic     /app/alembic
COPY admin-api/alembic.ini /app/alembic.ini

# 预建 MMDB 目录并归属 fangyu：挂载空命名卷时 Docker 会连属主一起复制进卷，
# 否则卷默认 root:root，admin-api 以 uid 1000 运行会写入失败。
RUN mkdir -p /data/mmdb && chown -R fangyu:fangyu /data/mmdb

USER fangyu
EXPOSE 8081

HEALTHCHECK --interval=15s --timeout=3s --retries=5 --start-period=20s \
  CMD curl -fsS http://127.0.0.1:${ADMIN_PORT}/v2/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# shell 形式：让 ${ADMIN_PORT} / ${ADMIN_WORKERS} 在运行时展开，
# exec 形式不做变量替换，端口会被固化成镜像构建时的值。
CMD gunicorn src.main:app -k uvicorn.workers.UvicornWorker \
     --bind "0.0.0.0:${ADMIN_PORT}" --workers "${ADMIN_WORKERS:-2}" \
     --timeout 60 --graceful-timeout 30 \
     --access-logfile - --error-logfile -
