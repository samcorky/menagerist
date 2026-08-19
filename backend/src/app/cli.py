import sys

try:
    from cyclopts import App
except ImportError:
    print("CLI Package not installed, please install `menagerist[cli]`")
    sys.exit(1)

from app.platform.app_info import load_app_info

app_info = load_app_info()

app = App(
    name=app_info.name,
    version=app_info.version,
)

if __name__ == "__main__":
    app()
