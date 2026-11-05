from pydantic import Field, SecretStr

from app.platform.config._base import MenageristBaseSettings


class IdentityCliSettings(MenageristBaseSettings, group="identity"):
    """Settings read only by the `menagerist identity` CLI, never by the server.

    `initial_password` comes from `MENAGERIST_IDENTITY_INITIAL_PASSWORD` or, preferably,
    a `menagerist_identity_initial_password` file in the secrets directory: environment
    variables show up in `docker inspect` and process listings.
    """

    initial_password: SecretStr | None = Field(
        default=None,
        min_length=1,
        description="Optional first-admin password; prefer its Docker secret file.",
    )


def get_identity_cli_settings() -> IdentityCliSettings:
    """Load the CLI settings fresh (the CLI is one short-lived process)."""
    return IdentityCliSettings()
