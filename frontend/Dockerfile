FROM node:22-slim AS deps

WORKDIR /app

# Only the lockfile determines install output, so this layer is cached
# across builds until dependencies actually change - unaffected by every
# other change below (generated client, source, config).
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM deps AS generate

# openapi.json changes far less often than application source. Isolating
# codegen in its own layer means source-only edits (the common case) skip
# regenerating the API client entirely and reuse this layer from cache.
COPY frontend/openapi.json frontend/openapi-ts.config.ts ./
RUN npm run generate

FROM generate AS build

COPY frontend/*.json frontend/*.js frontend/*.mjs frontend/*.ts frontend/*.cjs frontend/*.config.* ./
COPY frontend/src ./src
COPY frontend/static ./static

RUN npm run build

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

COPY --from=build --chown=10001:10001 /app/build /usr/share/nginx/html
COPY --chown=10001:10001 frontend/nginx.main.conf /etc/nginx/nginx.conf
COPY --chown=10001:10001 frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
