# syntax=docker/dockerfile:1.6
# Gateway API 生产镜像（多阶段构建）
ARG PYTHON_VERSION=3.11
ARG NODE_VERSION=20

# ── SDK 构建阶段 ──────────────────────────────────────────────────
# 把 client-sdk 编译成 UMD 包，随镜像发布到 /app/static/sdk，
# 由 main.py 挂在 /sdk 路径上对外分发。
#
# 为什么放在 gateway 镜像里：SDK 运行时只跟网关通信（/v2/decide、
# /v2/sdk/*），与网关同域分发可以免掉一次跨域预检，也让接入方只需
# 记住一个域名。dashboard-ui 是内网收口的后台，不适合承载公网流量。
FROM node:${NODE_VERSION}-alpine AS sdk-builder
WORKDIR /sdk
ARG PNPM_VERSION=9.15.9

COPY client-sdk/package.json client-sdk/pnpm-lock.yaml* ./
# pnpm-workspace.yaml 里 allowBuilds.esbuild=true 必须生效，
# 否则 esbuild 缺平台二进制，vite build 会直接失败。
# 该文件已显式声明 packages: ['.']，不会触发 workspace 解析报错。
COPY client-sdk/pnpm-workspace.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then \
      corepack enable \
      && if ! grep -q '"packageManager"' package.json; then \
           corepack prepare "pnpm@${PNPM_VERSION}" --activate; \
         fi \
      && pnpm install --frozen-lockfile; \
    else \
      npm install; \
    fi

COPY client-sdk .
RUN if [ -f pnpm-lock.yaml ]; then pnpm build; else npm run build; fi \
 && test -f dist/sd-sdk.min.js

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

# SDK 静态产物。main.py 用 StaticFiles 挂到 /sdk，浏览器最终从
# https://<网关域名>/sdk/sd-sdk.min.js 加载。
# 目录必须存在：GATEWAY_SDK_STATIC_DIR 指不到时 main.py 会跳过挂载，
# 那样 /sdk/* 会静默变成 404，比启动失败更难排查。
COPY --from=sdk-builder /sdk/dist /app/static/sdk

# Nginx-Lua 适配器脚本。后台接入指引里给的下载链接是
# <网关域名>/sdk/defense.lua，与 SDK 同目录分发，省一套托管。
COPY adapters/nginx-lua/defense.lua /app/static/sdk/defense.lua

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
