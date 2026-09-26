# 1) Сборка статики на node + pnpm
FROM node:22-alpine AS build

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    PNPM_STORE_DIR=/pnpm/store

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml ./

# Кеш магазина pnpm_between сборками: повторные билды не качают пакеты заново.
RUN --mount=type=cache,id=frontend-pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --prefer-offline --store-dir "$PNPM_STORE_DIR"

COPY tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts index.html ./
COPY public ./public
COPY src ./src

# Значения инлайнятся в бандл на этапе сборки, поэтому они ARG, а не ENV.
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_APP_NAME
ARG VITE_POLL_INTERVAL_MS
ARG VITE_API_TIMEOUT_MS
ARG VITE_MAP_STYLE_URL

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_APP_NAME=$VITE_APP_NAME \
    VITE_POLL_INTERVAL_MS=$VITE_POLL_INTERVAL_MS \
    VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS \
    VITE_MAP_STYLE_URL=$VITE_MAP_STYLE_URL

RUN pnpm build

# 2) Отдача nginx без root
FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# Подставляются из environment при старте контейнера.
ENV BACKEND_UPSTREAM=backend:8000 \
    LISTEN_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- "http://127.0.0.1:${LISTEN_PORT}/healthz" >/dev/null || exit 1
