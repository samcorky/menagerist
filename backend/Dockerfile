FROM debian:trixie-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
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

RUN uv python install

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --frozen \
        --no-install-workspace

COPY backend/ backend/

ARG SETUPTOOLS_SCM_PRETEND_VERSION=""
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
    SETUPTOOLS_SCM_PRETEND_VERSION=${SETUPTOOLS_SCM_PRETEND_VERSION} \
    MENAGERIST_BUILD_COMMIT_SHA=${MENAGERIST_BUILD_COMMIT_SHA} \
    MENAGERIST_BUILD_BRANCH=${MENAGERIST_BUILD_BRANCH} \
    MENAGERIST_BUILD_REPOSITORY_URL=${MENAGERIST_BUILD_REPOSITORY_URL} \
    MENAGERIST_BUILD_TIMESTAMP=${MENAGERIST_BUILD_TIMESTAMP} \
    MENAGERIST_BUILD_DIRTY=${MENAGERIST_BUILD_DIRTY} \
    uv sync --locked --no-editable --reinstall-package menagerist

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
            -type d -name '__pycache__' \
            -o -type d -name 'tests' \
            -o -type d -name 'test' \
        \) \
        -prune -exec rm -rf '{}' + \
    \
    && find /opt/python /app/.venv \
        \( \
            -name '*.pyc' \
            -o -name '*.pyo' \
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

FROM gcr.io/distroless/base-debian13:nonroot AS runtime

COPY --from=builder \
    /usr/lib/x86_64-linux-gnu/libgcc_s.so.1 \
    /usr/lib/x86_64-linux-gnu/libgcc_s.so.1

COPY --from=builder \
    /usr/lib/x86_64-linux-gnu/libstdc++.so.6 \
    /usr/lib/x86_64-linux-gnu/libstdc++.so.6

COPY --from=builder \
    /opt/terminfo-min \
    /usr/share/terminfo


WORKDIR /app

ENV \
    PATH="/opt/python/bin:/app/.venv/bin" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /opt/python /opt/python
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/backend/scripts/healthcheck.py /app/healthcheck.py

EXPOSE 8000

USER nonroot

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=10s \
    --retries=3 \
    CMD ["/app/.venv/bin/python", "/app/healthcheck.py"]

ENTRYPOINT ["menagerist"]
CMD ["serve", "--host", "0.0.0.0"]
