import structlog
from cyclopts import App

from app.platform.app_info import load_app_info
from app.platform.logging_config import configure_logging

configure_logging()
app_info = load_app_info()

logger = structlog.get_logger(__name__)

app = App(
    name=app_info.name,
    version=app_info.version,
)


if __name__ == "__main__":
    app()
