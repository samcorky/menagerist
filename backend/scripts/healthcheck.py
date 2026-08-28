import sys
import urllib.error
import urllib.request

try:
    urllib.request.urlopen(
        "http://127.0.0.1:8000/health",
        timeout=3,
    )
except (OSError, urllib.error.URLError):
    sys.exit(1)
