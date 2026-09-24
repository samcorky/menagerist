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
- the running container actually honours compose.yaml's hardening
  (read-only rootfs, uid 1000, dropped capabilities, no-new-privileges)
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
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

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


def get_container(client: docker.DockerClient) -> Container:
    """Return the running `menagerist` service container."""
    container_id = compose("ps", "-q", SERVICE).stdout.strip()
    if not container_id:
        raise SmokeTestError(f"no running container for service {SERVICE!r}")
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


def wait_healthy(client: docker.DockerClient, timeout: float = 90.0) -> None:
    """Poll the service's Docker healthcheck until it reports healthy."""
    print(f"waiting up to {timeout:.0f}s for {SERVICE} to report healthy...")
    container = get_container(client)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        container.reload()
        status = container.attrs["State"]["Health"]["Status"]
        if status == "healthy":
            return
        if status == "unhealthy":
            raise SmokeTestError(f"{SERVICE} reported unhealthy")
        time.sleep(2)
    raise SmokeTestError(f"{SERVICE} did not become healthy within {timeout:.0f}s")


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


def check_version_lockstep(client: docker.DockerClient) -> None:
    """Confirm the image's version label matches the running app's own report."""
    print("checking the image label and the running app report the same version...")
    label_version = client.images.get(IMAGE).labels.get(
        "org.opencontainers.image.version", ""
    )
    if not label_version:
        raise SmokeTestError("image has no org.opencontainers.image.version label")

    status, body = get("/api/version")
    if status != 200:
        raise SmokeTestError(f"/api/version returned {status}")
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
        check_hardening(client)
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
