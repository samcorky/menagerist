FROM node:22-slim AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/openapi.json ./

COPY frontend/ .

RUN npm run generate && npm run build

FROM ghcr.io/ammnt/nginx:1.31.4 AS runtime

ARG VERSION=""
ARG MENAGERIST_BUILD_COMMIT_SHA=""
ARG MENAGERIST_BUILD_TIMESTAMP=""

LABEL org.opencontainers.image.title="Menagerist frontend" \
      org.opencontainers.image.description="Static SPA frontend for Menagerist, a self-hostable personal knowledge graph for collectors." \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/samcorky/menagerist" \
      org.opencontainers.image.url="https://github.com/samcorky/menagerist" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${MENAGERIST_BUILD_COMMIT_SHA}" \
      org.opencontainers.image.created="${MENAGERIST_BUILD_TIMESTAMP}"

COPY --from=builder --chown=10001:10001 /app/build /usr/share/nginx/html
COPY --chown=10001:10001 frontend/nginx.main.conf /etc/nginx/nginx.conf
COPY --chown=10001:10001 frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
