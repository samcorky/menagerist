#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Check that a reverse proxy relays the app's early replies to an upload.

When the upload guard answers before the request body has been read (413 for an
over-limit upload, 401 for an unauthenticated one), the connection to the proxy
closes while the proxy is still writing. A proxy that sees the broken pipe
answers 502 instead of passing the reply on. The app drains the rest of the body
so that cannot happen; this test proves it through each proxy the documentation
shows, using `compose.proxy.yaml`: the real guard on Granian with no database,
behind nginx (with and without request buffering), Caddy or Traefik.

The failure is statistical, a few attempts in ten, so each scenario is repeated
`--attempts` times and every reply must be the expected one.

Assumes `menagerist:local` already exists (`poe docker-build`); the script never
builds it. It uses only the standard library and the `docker compose` CLI, so it
runs the same on Linux, macOS and Windows.
"""

import argparse
import collections
import http.client
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "compose.proxy.yaml"
IMAGE = "menagerist:local"
CHUNK = b"\0" * 1_000_000

# Compose profile (also the service name) -> host port, as in compose.proxy.yaml.
PROXIES = {"nginx": 18081, "nginx-buffered": 18082, "caddy": 18083, "traefik": 18084}


@dataclass(frozen=True)
class Scenario:
    """One body to post and the only status that is acceptable in reply."""

    name: str
    megabytes: int
    expected: int


SCENARIOS = (
    # Over the default 100 MiB media limit: refused 413 without reading the body.
    Scenario("over the limit (150 MB), refused 413", 150, 413),
    # Within the limit but answered 401 by the stub without reading the body.
    Scenario("unauthenticated (5 MB), answered 401", 5, 401),
)


def compose(*args: str, profile: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run `docker compose` against compose.proxy.yaml."""
    command = ["docker", "compose", "-f", str(COMPOSE_FILE)]
    if profile:
        command += ["--profile", profile]
    return subprocess.run(
        [*command, *args], check=False, text=True, capture_output=True
    )


def image_exists() -> bool:
    """Whether the locally built image is there."""
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def wait_until_answering(port: int, timeout: float = 60.0) -> bool:
    """Wait for the proxy to answer any HTTP request (a 401 or 502 still counts)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request("GET", "/")
            connection.getresponse().read()
            return True
        except OSError, http.client.HTTPException:
            time.sleep(1)
        finally:
            connection.close()
    return False


def post_body(port: int, megabytes: int) -> str:
    """POST that many megabytes to the upload route; return the status or the error."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        connection.putrequest("POST", "/api/v1/media")
        connection.putheader("Content-Type", "application/octet-stream")
        connection.putheader("Content-Length", str(megabytes * len(CHUNK)))
        connection.endheaders()
        try:
            for _ in range(megabytes):
                connection.send(CHUNK)
        except OSError:
            pass  # The proxy may have answered already; read it as a browser would.
        return str(connection.getresponse().status)
    except (OSError, http.client.HTTPException) as error:
        return type(error).__name__
    finally:
        connection.close()


def check_proxy(name: str, attempts: int) -> bool:
    """Bring one proxy up, run every scenario through it and tear it down."""
    port = PROXIES[name]
    print(f"\n{name} (127.0.0.1:{port})", flush=True)
    ok = True
    try:
        started = compose("up", "-d", "--wait", name, profile=name)
        if started.returncode != 0:
            print(f"  could not start:\n{started.stderr.strip()}")
            return False
        if not wait_until_answering(port):
            print("  never answered")
            ok = False
        else:
            for scenario in SCENARIOS:
                counts = collections.Counter(
                    post_body(port, scenario.megabytes) for _ in range(attempts)
                )
                good = set(counts) == {str(scenario.expected)}
                ok = ok and good
                shown = ", ".join(f"{k} x{v}" for k, v in sorted(counts.items()))
                print(f"  {'ok  ' if good else 'FAIL'} {scenario.name}: {shown}")
        if not ok:
            logs = compose("logs", "--tail", "5", "--no-color", name, profile=name)
            lines = (logs.stdout or logs.stderr).strip().splitlines()
            print("\n  last proxy log lines (truncated):")
            for line in lines:
                print(f"    {line[:200]}")
    finally:
        compose("down", "--remove-orphans", "--volumes", profile=name)
    return ok


def main() -> int:
    """Test the chosen proxies; return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "proxy",
        nargs="*",
        help=f"proxies to test, from {', '.join(PROXIES)} (default: all of them)",
    )
    parser.add_argument(
        "--attempts", type=int, default=20, help="repeats per scenario (default 20)"
    )
    args = parser.parse_args()
    unknown = [name for name in args.proxy if name not in PROXIES]
    if unknown:
        parser.error(f"unknown proxy: {', '.join(unknown)}")

    if not image_exists():
        print(f"{IMAGE} not found: run `poe docker-build` first", file=sys.stderr)
        return 2

    names = args.proxy or list(PROXIES)
    results = {name: check_proxy(name, args.attempts) for name in names}

    failed = [name for name, ok in results.items() if not ok]
    print()
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"all {len(names)} proxies relayed every early reply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
