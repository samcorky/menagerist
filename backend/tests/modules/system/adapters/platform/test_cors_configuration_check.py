from app.modules.system.adapters.platform.checks.cors_configuration_check import (
    CorsConfigurationCheck,
)
from app.modules.system.domain.readiness import CheckStatus
from app.platform.config.api import CORS_OPEN_HINT


async def test_warns_when_any_origin_is_allowed() -> None:
    """A `*` gives a warning that names the setting to change."""
    obs = (await CorsConfigurationCheck(["*"]).run())["configuration:corsOrigins"]

    assert obs.status is CheckStatus.WARN
    assert obs.observed_value == 1
    assert obs.output == CORS_OPEN_HINT
    assert "MENAGERIST_API_CORS_ORIGINS" in CORS_OPEN_HINT


async def test_warns_when_a_wildcard_sits_among_listed_origins() -> None:
    """One `*` is enough, whatever else is listed."""
    obs = (await CorsConfigurationCheck(["https://a.example", "*"]).run())[
        "configuration:corsOrigins"
    ]

    assert obs.status is CheckStatus.WARN


async def test_passes_for_no_origins() -> None:
    """Same-origin only is the safe default."""
    obs = (await CorsConfigurationCheck([]).run())["configuration:corsOrigins"]

    assert obs.status is CheckStatus.PASS
    assert obs.observed_value == 0
    assert obs.output is None


async def test_passes_for_explicit_origins() -> None:
    """Listing the sites that need access is fine."""
    obs = (await CorsConfigurationCheck(["https://app.example"]).run())[
        "configuration:corsOrigins"
    ]

    assert obs.status is CheckStatus.PASS
