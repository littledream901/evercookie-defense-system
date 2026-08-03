# syntax=docker/dockerfile:1.6
# Gateway API 生产镜像（多阶段构建）
ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl \
 && rm -rf /var/lib/apt/lists/*

COPY shared /build/shared
COPY gateway-api /build/gateway-api

# 两个包必须在同一条 pip 命令里安装。
# 分两条会失败：--prefix=/install 的 site-packages 不在构建期 sys.path 上，
# 第二条命令解析 gateway-api 的裸依赖 fangyu-shared 时看不到已装的本地包，
# 会转向 PyPI —— 而该包是 Proprietary，公网不存在。
RUN pip install --upgrade pip \
 && pip install --prefix=/install ./shared ./gateway-api

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    GATEWAY_PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 1000 --home /app fangyu

WORKDIR /app
COPY --from=builder /install /usr/local
COPY gateway-api/src /app/src

# 与 admin-api 对称地预建 MMDB 目录并归属 fangyu。gateway 只读该卷，
# 但两个容器都挂 mmdb-data 且无启动顺序约束：若 gateway 先挂载空卷，
# 卷会以 root:root 初始化，admin-api（uid 1000）后续上传 MMDB 会写入失败。
RUN mkdir -p /data/mmdb && chown -R fangyu:fangyu /data/mmdb

USER fangyu
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --retries=5 --start-period=15s \
  CMD curl -fsS http://127.0.0.1:${GATEWAY_PORT}/v2/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# shell 形式：让 ${GATEWAY_PORT} / ${GATEWAY_WORKERS} 在运行时展开，
# exec 形式不做变量替换，端口会被固化成镜像构建时的值。
CMD gunicorn src.main:app -k uvicorn.workers.UvicornWorker \
     --bind "0.0.0.0:${GATEWAY_PORT}" --workers "${GATEWAY_WORKERS:-4}" \
     --timeout 30 --graceful-timeout 20 \
     --access-logfile - --error-logfile -
