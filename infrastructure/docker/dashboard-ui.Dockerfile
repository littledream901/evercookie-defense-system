# syntax=docker/dockerfile:1.6
# Dashboard UI 静态资源镜像（构建 + Nginx 分发）
ARG NODE_VERSION=20
ARG NGINX_VERSION=1.27

FROM node:${NODE_VERSION}-alpine AS builder
WORKDIR /app

# pnpm 版本由 package.json 的 packageManager 字段锁定。
# 该字段缺失时 corepack 会拉 latest，而新版 pnpm 要求 Node 22+，
# 在 Node 20 上会以 ERR_UNKNOWN_BUILTIN_MODULE 失败 —— 故此处兜底显式指定。
ARG PNPM_VERSION=9.15.9

COPY dashboard-ui/package.json dashboard-ui/pnpm-lock.yaml* dashboard-ui/package-lock.json* ./
RUN if [ -f pnpm-lock.yaml ]; then \
      corepack enable \
      && if ! grep -q '"packageManager"' package.json; then \
           corepack prepare "pnpm@${PNPM_VERSION}" --activate; \
         fi \
      && pnpm install --frozen-lockfile; \
    else \
      npm ci; \
    fi

# 复制项目根目录的 .env.production（Vite 会从父目录读取）
COPY .env.production* /

COPY dashboard-ui .
RUN if [ -f pnpm-lock.yaml ]; then pnpm build; else npm run build; fi

FROM nginx:${NGINX_VERSION}-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY infrastructure/nginx/dashboard.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ || exit 1
