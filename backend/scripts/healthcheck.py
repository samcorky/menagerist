import sys
import urllib.error
import urllib.request


def main() -> int:
    """Docker health check for backend."""
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8000/api/health",
            timeout=3,
        ) as response:
            response.read()

            return 0 if response.status == 200 else 1

    except urllib.error.URLError, OSError, TimeoutError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
