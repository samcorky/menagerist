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

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=.git,target=/app/.git,ro \
    uv sync --locked --no-editable

# ---------------------------------------------------------------------------
# Strip things that aren't required at runtime.
#
# IMPORTANT:
# `uv python find` returns /app/.venv/bin/python3 because the venv is first
# in PATH. We therefore explicitly locate the Python installation under
# /opt/python.
#
# Keep terminfo because readline/curses-based CLI functionality requires it
# — but curate it down to the terminal types actually plausible in a
# container (real TTYs via `docker exec`, tmux/screen multiplexers, CI),
# rather than shipping ncurses-term's full database of hundreds of entries.
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM gcr.io/distroless/base-debian13:nonroot AS runtime

# Required by greenlet.
COPY --from=builder \
    /usr/lib/x86_64-linux-gnu/libgcc_s.so.1 \
    /usr/lib/x86_64-linux-gnu/libgcc_s.so.1

COPY --from=builder \
    /usr/lib/x86_64-linux-gnu/libstdc++.so.6 \
    /usr/lib/x86_64-linux-gnu/libstdc++.so.6

# Required by readline/curses-based CLI functionality — curated subset,
# see the cleanup RUN step in the builder stage for which terminals.
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
