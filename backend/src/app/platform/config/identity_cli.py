from pathlib import Path

from pydantic import SecretStr  # noqa: TC002 - pydantic resolves it at runtime

from app.platform.config._base import MenageristBaseSettings

# Where Docker and Compose mount secrets; a file named after the variable works.
SECRETS_DIR = Path("/run/secrets")


class IdentityCliSettings(MenageristBaseSettings):
    """Settings read only by the `menagerist identity` CLI, never by the server.

    `initial_password` comes from `MENAGERIST_INITIAL_PASSWORD` or, preferably,
    a `menagerist_initial_password` file in the secrets directory: environment
    variables show up in `docker inspect` and process listings.
    """

    initial_password: SecretStr | None = None


def get_identity_cli_settings() -> IdentityCliSettings:
    """Load the CLI settings fresh (the CLI is one short-lived process)."""
    return IdentityCliSettings(
        _secrets_dir=SECRETS_DIR if SECRETS_DIR.is_dir() else None
    )
