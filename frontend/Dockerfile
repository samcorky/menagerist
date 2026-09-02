FROM node:22-slim AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# frontend/openapi.json is produced by `poe dump-schema` before this build
# starts, so client generation never needs Python in this image.
COPY frontend/openapi.json ./

COPY frontend/ .

RUN npm run generate && npm run build

# ---------------------------------------------------------------------------
# Runtime: distroless nginx (ammnt/nginx), non-root uid/gid 10001, port 8080
#
# Built FROM scratch with /etc/nginx chowned 10001:10001 and locked to 550
# (dirs) / 440 (files) — only uid or gid 10001 can traverse it, so the
# container MUST run as 10001:10001 (see compose.dev.yaml). Files added here
# are chowned to match; the base image ships no html directory of its own,
# and its default.conf/nginx.conf are placeholders we fully replace.
# ---------------------------------------------------------------------------
FROM ghcr.io/ammnt/nginx:1.31.4 AS runtime

COPY --from=builder --chown=10001:10001 /app/build /usr/share/nginx/html
COPY --chown=10001:10001 frontend/nginx.main.conf /etc/nginx/nginx.conf
COPY --chown=10001:10001 frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
