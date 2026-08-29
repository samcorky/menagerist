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
# Runtime: distroless nginx (Chainguard), non-root, port 8080
# ---------------------------------------------------------------------------
FROM cgr.dev/chainguard/nginx AS runtime

COPY --from=builder /app/build /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
