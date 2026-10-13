import pytest

from app.modules.system.adapters.platform.checks.proxy_configuration_check import (
    ProxyConfigurationCheck,
)
from app.modules.system.domain.readiness import CheckStatus
from app.platform import proxy_signals
from app.platform.proxy_signals import ProxySignal


@pytest.fixture(autouse=True)
def _clean() -> None:
    proxy_signals.reset()


async def test_passes_when_nothing_suspicious_was_seen() -> None:
    """No signals, no warning."""
    result = await ProxyConfigurationCheck().run()

    obs = result["proxy:configuration"]
    assert obs.status is CheckStatus.PASS
    assert obs.observed_value == 0
    assert obs.observed_unit == "flagged requests"
    assert obs.output is None


@pytest.mark.parametrize(
    ("signal", "words"),
    [
        (ProxySignal.UNTRUSTED_FORWARDING, "forwarding headers"),
        (ProxySignal.ORIGIN_MISMATCH, "origin differs"),
    ],
)
async def test_warns_with_a_hint_for_each_signal(
    signal: ProxySignal, words: str
) -> None:
    """A signal gives a warning that names the setting to look at."""
    proxy_signals.record(signal)

    obs = (await ProxyConfigurationCheck().run())["proxy:configuration"]

    assert obs.status is CheckStatus.WARN
    assert obs.observed_value == 1
    assert obs.output is not None
    assert words in obs.output
    assert "MENAGERIST_TRUSTED_PROXIES" in obs.output


async def test_both_hints_appear_when_both_signals_were_seen() -> None:
    """Each signal contributes its own hint."""
    proxy_signals.record(ProxySignal.UNTRUSTED_FORWARDING)
    proxy_signals.record(ProxySignal.ORIGIN_MISMATCH)

    obs = (await ProxyConfigurationCheck().run())["proxy:configuration"]

    assert obs.observed_value == 2
    assert obs.output is not None
    assert "forwarding headers" in obs.output
    assert "origin differs" in obs.output
