# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS builder

WORKDIR /app

ARG VITE_API_BASE_URL=/api/v1
ARG VITE_WHATSAPP_GATEWAY_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_WHATSAPP_GATEWAY_BASE_URL=${VITE_WHATSAPP_GATEWAY_BASE_URL}

COPY . .

RUN set -eux; \
    if [ -f package-lock.json ]; then \
        npm ci && npm run build; \
    elif [ -f pnpm-lock.yaml ]; then \
        corepack enable && pnpm install --frozen-lockfile && pnpm build; \
    elif [ -f yarn.lock ]; then \
        corepack enable && yarn install --frozen-lockfile && yarn build; \
    elif [ -f package.json ]; then \
        echo "A package lock file is required for reproducible production builds." >&2; \
        exit 1; \
    else \
        mkdir -p dist; \
        cp docker/placeholder.html dist/index.html; \
    fi; \
    test -f dist/index.html


FROM nginx:1.27-alpine AS runtime

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
