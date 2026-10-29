#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "docker>=7.2.0",
# ]
# ///
"""Smoke test the built `menagerist:local` image through its own compose.yaml.

Brings the stack up with `docker compose` rather than a hand-rolled `docker
run`, so every check runs against exactly what a real deployment gets: the
hardening flags (read-only rootfs, dropped capabilities, non-root user,
tmpfs mounts) and the `--migrate` startup flag all come from compose.yaml
itself, never reimplemented here as flags that could quietly drift from it.
Compose orchestration (`up`/`down`/`run`/`logs`) isn't exposed by the Docker
Engine API, so those still shell out to the `docker compose` CLI; everything
that's plain container/image introspection uses the `docker` SDK instead of
parsing `docker inspect` Go-template output.

Checks:
- the stack comes up and the menagerist service reports healthy (proves
  `serve --migrate` applied migrations and reached the database)
- the worker service reports healthy too, and its `worker-health` probe, run
  the way the healthcheck runs it, finishes well inside the healthcheck's own
  timeout (a CLI that imports too much times out and the worker is marked
  unhealthy while working perfectly)
- the running container actually honours compose.yaml's hardening
  (read-only rootfs, uid 1000, dropped capabilities, no-new-privileges)
- the granian worker's own boot (import + app construction) stays fast,
  catching regressions like a heavy import pulled in at module scope
- the SPA and API are both served correctly on one port (shell, client-side
  route fallback, missing-asset 404, unknown /api/* 404)
- the image's version label and the running app's reported version match
  (proves the single VERSION build arg reaches both)
- `migrate upgrade` still works standalone, for multi-instance deployments
  that don't use --migrate

Assumes `menagerist:local` already exists (`poe docker-build` /
`docker buildx bake -f docker-bake.hcl local`) - this script never builds
it, only exercises it.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import docker
from docker.errors import DockerException, NotFound

if TYPE_CHECKING:
    from docker.models.containers import Container

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "compose.yaml"
COMPOSE_OVERRIDE_FILE = REPO_ROOT / "compose.smoke.yaml"
PROJECT_NAME = "menagerist-smoke"
BASE_URL = "http://localhost:18080"
SERVICE = "menagerist"
WORKER_SERVICE = "worker"
IMAGE = "menagerist:local"


class SmokeTestError(RuntimeError):
    """A smoke test check failed."""


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a `docker compose` subcommand against compose.yaml.

    Compose orchestration (YAML anchors, env_file, healthcheck-gated
    depends_on) has no equivalent in the Docker Engine API, so this is the
    only faithful way to drive it - the `docker` SDK below is only used for
    read-only introspection of what compose brought up.

    Runs under its own project name with compose.smoke.yaml layered on top,
    so this never collides with container names, the published port, or the
    bridge network of a dev stack already running from compose.yaml.
    """
    return subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "-f",
            str(COMPOSE_OVERRIDE_FILE),
            "-p",
            PROJECT_NAME,
            *args,
        ],
        capture_output=True,
        text=True,
        check=check,
        cwd=REPO_ROOT,
    )


def get_client() -> docker.DockerClient:
    """Connect to the local Docker daemon, with a clear error if unreachable."""
    try:
        return docker.from_env()
    except DockerException as exc:
        raise SmokeTestError(f"could not reach Docker: {exc}") from exc


def get(path: str) -> tuple[int, bytes]:
    """GET `path` from the running stack and return (status, body)."""
    request = urllib.request.Request(f"{BASE_URL}{path}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def get_container(client: docker.DockerClient, service: str = SERVICE) -> Container:
    """Return the running container for a compose service."""
    container_id = compose("ps", "-q", service).stdout.strip()
    if not container_id:
        raise SmokeTestError(f"no running container for service {service!r}")
    try:
        return client.containers.get(container_id)
    except NotFound as exc:
        raise SmokeTestError(f"container {container_id!r} disappeared") from exc


def require_image_built(client: docker.DockerClient) -> None:
    """Fail fast with a clear message if `menagerist:local` hasn't been built."""
    try:
        client.images.get(IMAGE)
    except NotFound as exc:
        raise SmokeTestError(
            f"{IMAGE!r} isn't built - run `poe docker-build` "
            + "(docker buildx bake -f docker-bake.hcl local) first"
        ) from exc


def wait_healthy(
    client: docker.DockerClient, service: str = SERVICE, timeout: float = 90.0
) -> None:
    """Poll a service's Docker healthcheck until it reports healthy."""
    print(f"waiting up to {timeout:.0f}s for {service} to report healthy...")
    container = get_container(client, service)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        container.reload()
        status = container.attrs["State"]["Health"]["Status"]
        if status == "healthy":
            return
        if status == "unhealthy":
            raise SmokeTestError(f"{service} reported unhealthy")
        time.sleep(2)
    raise SmokeTestError(f"{service} did not become healthy within {timeout:.0f}s")


def check_hardening(client: docker.DockerClient) -> None:
    """Confirm the running container actually honours compose.yaml's hardening."""
    print("checking hardening (read-only rootfs, non-root, dropped capabilities)...")
    container = get_container(client)
    host_config = container.attrs["HostConfig"]

    if not host_config["ReadonlyRootfs"]:
        raise SmokeTestError("expected a read-only rootfs")

    user = container.attrs["Config"]["User"]
    if user != "1000:1000":
        raise SmokeTestError(f"expected user 1000:1000, got {user!r}")

    cap_drop = host_config.get("CapDrop") or []
    if "ALL" not in cap_drop:
        raise SmokeTestError(f"expected capabilities dropped (ALL), got {cap_drop!r}")

    # The Engine API reports capabilities back with the `CAP_` prefix
    # normalized on, even though compose.yaml (and `docker compose`) accept
    # the bare name.
    cap_add = host_config.get("CapAdd") or []
    if "CAP_NET_BIND_SERVICE" not in cap_add:
        raise SmokeTestError(f"expected NET_BIND_SERVICE added back, got {cap_add!r}")

    security_opt = host_config.get("SecurityOpt") or []
    if "no-new-privileges:true" not in security_opt:
        raise SmokeTestError(f"expected no-new-privileges, got {security_opt!r}")

    # container.top() reads the process table from the host side, so this
    # works even though the distroless image has no shell to exec into.
    # `pid` must be requested alongside `uid` - the daemon uses it to
    # correlate ps output and errors ("Couldn't find PID field") without it.
    top = container.top(ps_args="-o pid,uid")
    uid_index = top["Titles"].index("UID")
    uids = {row[uid_index] for row in top["Processes"]}
    if uids - {"1000"}:
        raise SmokeTestError(f"process(es) not running as uid 1000: {uids}")


_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_LOG_TIMESTAMP = re.compile(r"^(\S+Z)")

# Generous relative to the ~0.6-0.8s this takes on a modern dev machine -
# wide enough to absorb slow CI/NAS-class hardware, tight enough to still
# catch a regression like jsonschema[format-nongpl] silently adding ~1s of
# regex-compilation import cost (see backend/pyproject.toml history).
# Set SMOKE_MAX_WORKER_STARTUP_SECONDS to loosen it on a slow host.
_MAX_WORKER_STARTUP_SECONDS = float(
    os.environ.get("SMOKE_MAX_WORKER_STARTUP_SECONDS", "5.0")
)


def _log_line_timestamp(logs: str, marker: str) -> float:
    """Return the Unix timestamp of the first log line containing `marker`."""
    for line in logs.splitlines():
        clean = _ANSI_ESCAPE.sub("", line)
        if marker not in clean:
            continue
        match = _LOG_TIMESTAMP.match(clean)
        if not match:
            continue
        return (
            datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S.%fZ")
            .replace(tzinfo=UTC)
            .timestamp()
        )
    raise SmokeTestError(f"no log line found containing {marker!r}")


def check_startup_time(client: docker.DockerClient) -> None:
    """Confirm the app's own worker boot (import + app construction) stays fast.

    Deliberately measures just the granian worker's spawn-to-ready gap, not
    the whole container's time-to-healthy - that also includes Postgres
    startup and migrations, which have nothing to do with app import cost
    and would make this check noisy without adding any regression coverage.
    """
    print("checking the worker starts up quickly...")
    logs = get_container(client).logs().decode()
    spawned_at = _log_line_timestamp(logs, "Spawning worker-1")
    started_at = _log_line_timestamp(logs, "Started worker-1")
    duration = started_at - spawned_at

    startup_lines: list[str] = []
    in_startup = False
    for line in logs.splitlines():
        clean = _ANSI_ESCAPE.sub("", line)
        if "Spawning worker-1" in clean:
            in_startup = True
        if in_startup:
            startup_lines.append(clean)
        if "Started worker-1" in clean and in_startup:
            break

    print(f"  worker started in {duration:.2f}s")
    if startup_lines:
        print("  startup logs:")
        for line in startup_lines:
            print(f"    {line}")

    if duration > _MAX_WORKER_STARTUP_SECONDS:
        raise SmokeTestError(
            f"worker took {duration:.2f}s to start "
            + f"(limit {_MAX_WORKER_STARTUP_SECONDS:.2f}s) - "
            + "check for a heavy import pulled in at module scope"
        )


# The healthcheck kills a probe at its timeout (10s in compose.yaml). Half of that
# leaves room for a busy host, where a probe that only just fits will start flapping.
_PROBE_BUDGET_FRACTION = 0.5


def _timed_exec(container: Container, command: list[str]) -> tuple[int, float, str]:
    """Run a command in the container and return (exit code, seconds, output)."""
    started = time.monotonic()
    result = container.exec_run(command, demux=False)
    seconds = time.monotonic() - started
    output = result.output if isinstance(result.output, bytes) else b""
    exit_code = -1 if result.exit_code is None else result.exit_code
    return exit_code, seconds, output.decode(errors="replace")


def check_cli_probe_time(client: docker.DockerClient) -> None:
    """Confirm the worker's health probe finishes well inside its healthcheck timeout.

    Runs `menagerist worker-health` in the worker container, exactly as the
    healthcheck does, and compares it with the timeout compose.yaml gives it.
    `--version` is timed too: it does the same CLI import without touching the
    database, so a slow probe can be told apart as an import regression or a
    slow check.
    """
    print("checking the CLI health probe is fast enough for its healthcheck...")
    container = get_container(client, WORKER_SERVICE)
    healthcheck = container.attrs["Config"].get("Healthcheck") or {}
    timeout = healthcheck.get("Timeout", 10_000_000_000) / 1e9
    budget = timeout * _PROBE_BUDGET_FRACTION

    code, import_seconds, _ = _timed_exec(container, ["menagerist", "--version"])
    if code != 0:
        raise SmokeTestError(f"`menagerist --version` failed (exit {code})")
    code, probe_seconds, output = _timed_exec(
        container, ["menagerist", "worker-health"]
    )

    print(f"  CLI import (--version): {import_seconds:.2f}s")
    print(f"  worker-health probe:    {probe_seconds:.2f}s")
    print(f"  healthcheck timeout:    {timeout:.0f}s (limit {budget:.1f}s)")
    if code != 0:
        raise SmokeTestError(f"`worker-health` exited {code}: {output.strip()}")
    if probe_seconds > budget:
        raise SmokeTestError(
            f"the health probe took {probe_seconds:.2f}s, over {budget:.1f}s of the "
            + f"{timeout:.0f}s healthcheck timeout - check for a heavy import "
            + "pulled in at module scope in the CLI"
        )


# Jobs the image must register; extra ones are fine, so a new job needs no change here.
EXPECTED_JOBS = frozenset(
    {
        "scheduling.prune_runs",
        "backup.create",
        "backup.prune_exports",
        "identity.purge_expired",
        "media.cleanup",
        "media.remove_stray_files",
        "data.purge_deleted",
    }
)


def _exec_json(container: Container, command: list[str]) -> object:
    """Run a CLI command in the container and parse what it prints on stdout.

    Logs go to stderr, so the streams are kept apart rather than merged.
    """
    result = container.exec_run(command, demux=True)
    # The stubs type `output` for every `demux` mode; with `demux=True` it is a pair.
    stdout, stderr = cast("tuple[bytes | None, bytes | None]", result.output)
    stdout = stdout or b""
    stderr = stderr or b""
    if result.exit_code != 0:
        raise SmokeTestError(
            f"`{' '.join(command)}` exited {result.exit_code}: "
            + f"{stdout.decode(errors='replace')}"
            + f"{stderr.decode(errors='replace')}".strip()
        )
    try:
        return json.loads(stdout.decode())
    except json.JSONDecodeError as error:
        raise SmokeTestError(
            f"`{' '.join(command)}` did not print JSON: {stdout!r}"
        ) from error


def check_worker_jobs(client: docker.DockerClient) -> None:
    """Confirm the worker image registers every job and can run one end to end.

    A job's settings, wiring and storage access all come together only in the
    real container, which is read-only and non-root, so list the catalogue and
    run one job that needs no setup to completion.
    """
    print("checking the worker's jobs register and one runs to completion...")
    container = get_container(client, WORKER_SERVICE)
    listed = _exec_json(container, ["menagerist", "job", "list", "--json"])
    if not isinstance(listed, list):
        raise SmokeTestError(f"`job list` did not print a list: {listed!r}")
    registered = {item["job_key"] for item in listed}
    if missing := EXPECTED_JOBS - registered:
        raise SmokeTestError(f"the worker does not register: {sorted(missing)}")

    ran = _exec_json(
        container, ["menagerist", "job", "run", "scheduling.prune_runs", "--json"]
    )
    if not isinstance(ran, dict) or ran.get("status") != "succeeded":
        raise SmokeTestError(
            f"`job run scheduling.prune_runs` did not succeed: {ran!r}"
        )
    print(f"  {len(registered)} jobs registered; scheduling.prune_runs succeeded")


def check_version_lockstep(client: docker.DockerClient) -> None:
    """Confirm the image's version label matches the running app's own report."""
    print("checking the image label and the running app report the same version...")
    label_version = client.images.get(IMAGE).labels.get(
        "org.opencontainers.image.version", ""
    )
    if not label_version:
        raise SmokeTestError("image has no org.opencontainers.image.version label")

    status, body = get("/api/v1/system/version")
    if status != 200:
        raise SmokeTestError(f"/api/v1/system/version returned {status}")
    reported_version = json.loads(body)["current_version"]

    if label_version != reported_version:
        raise SmokeTestError(
            f"version mismatch: image label {label_version!r} != "
            + f"running app {reported_version!r}"
        )


def check_spa_and_api() -> None:
    """Confirm the SPA shell and the API are both served correctly on one port."""
    print("checking the SPA and API are both served correctly...")

    status, body = get("/")
    if status != 200 or b"<html" not in body.lower():
        raise SmokeTestError(f"SPA shell not served at /: status={status}")

    status, body = get("/some/client/side/route")
    if status != 200 or b"<html" not in body.lower():
        raise SmokeTestError("client-side route did not fall back to the SPA shell")

    status, _ = get("/_app/immutable/does-not-exist.deadbeef.js")
    if status != 404:
        raise SmokeTestError(f"missing hashed asset should 404, got {status}")

    status, _ = get("/api/does-not-exist")
    if status != 404:
        raise SmokeTestError(f"unknown /api/* route should 404, got {status}")

    status, _ = get("/api/health")
    if status != 200:
        raise SmokeTestError(f"/api/health returned {status}")

    status, body = get("/api/health/ready")
    if status != 200:
        raise SmokeTestError(f"/api/health/ready returned {status}: {body!r}")


def check_migrate_upgrade_standalone() -> None:
    """Confirm `migrate upgrade` still works as a standalone CLI invocation."""
    print("checking `migrate upgrade` still works standalone...")
    result = compose("run", "--rm", SERVICE, "migrate", "upgrade", check=False)
    if result.returncode != 0:
        raise SmokeTestError(
            f"`migrate upgrade` failed (exit {result.returncode}):\n{result.stderr}"
        )


def main() -> int:
    """Bring the stack up via compose.yaml, run every check, then tear it down."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave the stack running after the checks (for debugging).",
    )
    args = parser.parse_args()

    client: docker.DockerClient | None = None

    try:
        client = get_client()
        require_image_built(client)

        print(f"bringing up the stack from {COMPOSE_FILE} ...")
        compose("up", "-d")

        wait_healthy(client)
        wait_healthy(client, WORKER_SERVICE, timeout=150.0)
        check_cli_probe_time(client)
        check_worker_jobs(client)
        check_hardening(client)
        check_startup_time(client)
        check_version_lockstep(client)
        check_spa_and_api()
        check_migrate_upgrade_standalone()
    except SmokeTestError as exc:
        print(f"\nSMOKE TEST FAILED: {exc}", file=sys.stderr)
        print("\n--- menagerist logs ---", file=sys.stderr)
        print(compose("logs", SERVICE, check=False).stdout, file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            compose("down", "-v", check=False)
        if client is not None:
            client.close()

    print("\nsmoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
