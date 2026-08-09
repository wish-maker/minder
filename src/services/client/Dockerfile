# Multi-stage build: compile the React/Vite app, then serve the static
# output with nginx. This is the first Node-based service in the repo --
# everything else here is a Python/uvicorn service.

FROM node:22.14.0-alpine AS builder

WORKDIR /app
COPY src/services/client/package.json src/services/client/package-lock.json ./
RUN npm ci

COPY src/services/client/ .

# Baked in at BUILD time (Vite convention) -- changing this requires a
# rebuild, not just a container restart. See docker-compose.yml's build.args
# and .env.example's CLIENT_API_BASE_URL.
#
# Defaults to the gateway's own loopback dev port, NOT the Traefik hostname:
# confirmed live that api.minder.local isn't resolvable without a manual
# /etc/hosts entry (same as every other *.minder.local route -- "no real DNS
# by default"). localhost:8000 is what a fresh clone can already reach with
# zero setup (api-gateway's own loopback port), matching the zero-config
# property the old same-origin pages had. Override for a real deployment
# where client.minder.local is set up (which already implies api.minder.local
# is too).
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# Same pinned nginx:alpine already used for ollama-router elsewhere in this
# repo (docker/services/ollama-router), for a single vetted base image
# rather than introducing a second nginx variant.
FROM nginx:1.31.3-alpine

RUN addgroup -g 1000 minderclient && adduser -D -u 1000 -G minderclient minderclient \
    && chown -R minderclient:minderclient /var/cache/nginx /var/run /var/log/nginx \
    && touch /var/run/nginx.pid && chown minderclient:minderclient /var/run/nginx.pid

COPY --from=builder /app/dist /usr/share/nginx/html
COPY src/services/client/nginx.conf /etc/nginx/conf.d/default.conf

USER minderclient

EXPOSE 8009

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8009/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
