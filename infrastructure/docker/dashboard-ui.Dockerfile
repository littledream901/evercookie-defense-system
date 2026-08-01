# syntax=docker/dockerfile:1.6
# Dashboard UI 静态资源镜像（构建 + Nginx 分发）
ARG NODE_VERSION=20
ARG NGINX_VERSION=1.27

FROM node:${NODE_VERSION}-alpine AS builder
WORKDIR /app

COPY dashboard-ui/package.json dashboard-ui/pnpm-lock.yaml* dashboard-ui/package-lock.json* ./
RUN if [ -f pnpm-lock.yaml ]; then \
      corepack enable && pnpm install --frozen-lockfile; \
    else \
      npm ci; \
    fi

COPY dashboard-ui .
RUN if [ -f pnpm-lock.yaml ]; then pnpm build; else npm run build; fi

FROM nginx:${NGINX_VERSION}-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY infrastructure/nginx/dashboard.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ || exit 1
