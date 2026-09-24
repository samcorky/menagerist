FROM debian:trixie-slim AS backend-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        ncurses-term \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv@sha256:95f2aa1fe59274951cfe9b0cbc7972e879ff1004bc8945d130a32eb0dbd85945 \
    /uv /uvx /bin/

WORKDIR /app

ENV \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

COPY .python-version ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv python install

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --frozen \
        --no-install-workspace

COPY backend/ backend/

ARG VERSION=""
ARG MENAGERIST_BUILD_COMMIT_SHA=""
ARG MENAGERIST_BUILD_BRANCH=""
ARG MENAGERIST_BUILD_REPOSITORY_URL=""
ARG MENAGERIST_BUILD_TIMESTAMP=""
ARG MENAGERIST_BUILD_DIRTY=""

# Keep metadata tied to the repo root during build.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=.git,target=/app/.git,ro \
    --mount=type=bind,source=.,target=/src,ro \
    GIT_DIR=/app/.git GIT_WORK_TREE=/src \
    SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION} \
    MENAGERIST_BUILD_COMMIT_SHA=${MENAGERIST_BUILD_COMMIT_SHA} \
    MENAGERIST_BUILD_BRANCH=${MENAGERIST_BUILD_BRANCH} \
    MENAGERIST_BUILD_REPOSITORY_URL=${MENAGERIST_BUILD_REPOSITORY_URL} \
    MENAGERIST_BUILD_TIMESTAMP=${MENAGERIST_BUILD_TIMESTAMP} \
    MENAGERIST_BUILD_DIRTY=${MENAGERIST_BUILD_DIRTY} \
    uv sync --locked --no-editable --reinstall-package menagerist

# The frontend build needs the API's OpenAPI schema to generate its typed
# client against - dump it now while the app is fully built, no DB needed
# (create_app().openapi() only introspects routes).
RUN mkdir -p /out \
    && .venv/bin/menagerist schema dump --output /out/openapi.json

# Keep the minimal terminal database needed for readline/curses CLI usage.
RUN PYTHON_DIR="$(find /opt/python -mindepth 1 -maxdepth 1 -type d -name 'cpython-*' -print -quit)" \
    && echo "Python runtime: ${PYTHON_DIR}" \
    \
    && echo "=== Before cleanup ===" \
    && du -sh "${PYTHON_DIR}" \
    && du -sh /usr/share/terminfo \
    \
    && rm -rf \
        "${PYTHON_DIR}/include" \
        "${PYTHON_DIR}/lib/tcl"* \
        "${PYTHON_DIR}/lib/tk"* \
        "${PYTHON_DIR}/lib/libtcl"* \
        "${PYTHON_DIR}/lib/libtk"* \
        "${PYTHON_DIR}/lib/python3.14/idlelib" \
        "${PYTHON_DIR}/lib/python3.14/tkinter" \
        "${PYTHON_DIR}/lib/python3.14/turtledemo" \
        "${PYTHON_DIR}/lib/python3.14/ensurepip" \
        "${PYTHON_DIR}/lib/python3.14/site-packages/pip" \
        "${PYTHON_DIR}/lib/python3.14/site-packages/setuptools" \
        "${PYTHON_DIR}"/lib/python3.14/config-3.14* \
    \
    && find /opt/python /app/.venv \
        \( \
            -type d -name 'tests' \
            -o -type d -name 'test' \
        \) \
        -prune -exec rm -rf '{}' + \
    \
    && find /opt/python /app/.venv \
        \( \
            -name '*.pyo' \
            -o -name '*.a' \
            -o -name '_test*.so' \
            -o -name '_ctypes_test*.so' \
            -o -name 'xxlimited*.so' \
            -o -name 'xxsubtype*.so' \
        \) \
        -delete \
    \
    && mkdir -p /opt/terminfo-min \
    && for term in xterm xterm-256color screen screen-256color \
                   tmux tmux-256color linux vt100 ansi dumb; do \
         first_char="$(printf '%s' "${term}" | cut -c1)"; \
         if [ -f "/usr/share/terminfo/${first_char}/${term}" ]; then \
             mkdir -p "/opt/terminfo-min/${first_char}"; \
             cp "/usr/share/terminfo/${first_char}/${term}" \
                "/opt/terminfo-min/${first_char}/${term}"; \
         fi; \
       done \
    \
    && echo "=== greenlet dependencies ===" \
    && ldd /app/.venv/lib/python3.14/site-packages/greenlet/_greenlet*.so \
    \
    && echo "=== After cleanup ===" \
    && du -sh "${PYTHON_DIR}" \
    && du -sh /app/.venv \
    && du -sh /opt/terminfo-min

# libgcc_s/libstdc++ are needed at runtime (e.g. by greenlet's C extension)
# but distroless doesn't ship them. Mirror wherever this build's own libc
# multiarch directory actually is (x86_64-linux-gnu, aarch64-linux-gnu, ...)
# under /opt/runtime-libs, so the runtime stage's COPY below works
# unmodified on every platform docker buildx bake builds for.
RUN for lib in libgcc_s.so.1 libstdc++.so.6; do \
        src="$(find /usr/lib -maxdepth 2 -name "${lib}" -print -quit)"; \
        [ -n "${src}" ] || { echo "missing ${lib}" >&2; exit 1; }; \
        dest="/opt/runtime-libs${src#/usr/lib}"; \
        mkdir -p "$(dirname "${dest}")"; \
        cp "${src}" "${dest}"; \
    done

RUN mkdir -p /data/media && chown 1000:1000 /data/media


FROM node:22-slim AS frontend-deps

WORKDIR /app

# Only the lockfile determines install output, so this layer is cached
# across builds until dependencies actually change - unaffected by every
# other change below (generated client, source, config).
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci


FROM frontend-deps AS frontend-generate

# The schema changes far less often than application source. Isolating
# codegen in its own layer means source-only edits (the common case) skip
# regenerating the API client entirely and reuse this layer from cache.
COPY frontend/openapi-ts.config.ts ./
COPY --from=backend-builder /out/openapi.json ./openapi.json
RUN npm run generate


FROM frontend-generate AS frontend-build

COPY frontend/*.json frontend/*.js frontend/*.mjs frontend/*.ts frontend/*.cjs frontend/*.config.* ./
COPY frontend/src ./src
COPY frontend/static ./static
# Keep the client generated from the schema rather than the ignored copy in the
# build context.
COPY --from=frontend-generate /app/src/lib/api/generated ./src/lib/api/generated

RUN npm run build


FROM gcr.io/distroless/base-debian13:nonroot AS runtime

ARG VERSION=""
ARG MENAGERIST_BUILD_COMMIT_SHA=""
ARG MENAGERIST_BUILD_BRANCH=""
ARG MENAGERIST_BUILD_REPOSITORY_URL=""
ARG MENAGERIST_BUILD_TIMESTAMP=""
ARG MENAGERIST_BUILD_DIRTY=""

LABEL org.opencontainers.image.title="Menagerist" \
      org.opencontainers.image.description="A lightweight, self-hostable and flexible platform for organising the things you care about." \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/samcorky/menagerist" \
      org.opencontainers.image.url="https://github.com/samcorky/menagerist" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${MENAGERIST_BUILD_COMMIT_SHA}" \
      org.opencontainers.image.created="${MENAGERIST_BUILD_TIMESTAMP}"

COPY --from=backend-builder /opt/runtime-libs/ /usr/lib/

COPY --from=backend-builder \
    /opt/terminfo-min \
    /usr/share/terminfo

WORKDIR /app

ENV \
    PATH="/opt/python/bin:/app/.venv/bin" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MENAGERIST_FRONTEND_DIST_PATH=/app/frontend

COPY --from=backend-builder /opt/python /opt/python
COPY --from=backend-builder /app/.venv /app/.venv
COPY --from=backend-builder /app/backend/scripts/healthcheck.py /app/healthcheck.py
COPY --from=backend-builder --chown=1000:1000 /data/media /data/media
COPY --from=frontend-build --chown=1000:1000 /app/build /app/frontend

EXPOSE 8000

USER 1000:1000

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=10s \
    --retries=3 \
    CMD ["/app/.venv/bin/python", "/app/healthcheck.py"]

ENTRYPOINT ["menagerist"]
CMD ["serve", "--host", "0.0.0.0", "--migrate"]
