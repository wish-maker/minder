# Multi-stage build: compile the React/Vite app, then serve the static
# output with nginx. This is the first Node-based service in the repo --
# everything else here is a Python/uvicorn service.

FROM node:22.14.0-alpine AS builder

WORKDIR /app
COPY src/services/admin-ui/package.json src/services/admin-ui/package-lock.json ./
RUN npm ci

COPY src/services/admin-ui/ .

# Baked in at BUILD time (Vite convention) -- changing this requires a
# rebuild, not just a container restart. See docker-compose.yml's build.args
# and .env.example's ADMIN_UI_API_BASE_URL.
ARG VITE_API_BASE_URL=https://api.minder.local
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# Same pinned nginx:alpine already used for ollama-router elsewhere in this
# repo (docker/services/ollama-router), for a single vetted base image
# rather than introducing a second nginx variant.
FROM nginx:1.31.3-alpine

RUN addgroup -g 1000 adminui && adduser -D -u 1000 -G adminui adminui \
    && chown -R adminui:adminui /var/cache/nginx /var/run /var/log/nginx \
    && touch /var/run/nginx.pid && chown adminui:adminui /var/run/nginx.pid

COPY --from=builder /app/dist /usr/share/nginx/html
COPY src/services/admin-ui/nginx.conf /etc/nginx/conf.d/default.conf

USER adminui

EXPOSE 8009

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8009/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
