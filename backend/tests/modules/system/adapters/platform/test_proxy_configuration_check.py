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


UNTRUSTED = "configuration:proxyUntrustedForwarding"
MISMATCH = "configuration:proxyOriginMismatch"
PUBLIC_MISMATCH = "configuration:proxyPublicOriginMismatch"
INSECURE = "configuration:proxyInsecureOrigin"


async def test_passes_when_nothing_suspicious_was_seen() -> None:
    """No signals: one passing observation per signal."""
    result = await ProxyConfigurationCheck().run()

    assert set(result) == {UNTRUSTED, MISMATCH, PUBLIC_MISMATCH, INSECURE}
    for obs in result.values():
        assert obs.status is CheckStatus.PASS
        assert obs.observed_value == 0
        assert obs.observed_unit == "flagged requests"
        assert obs.output is None


@pytest.mark.parametrize(
    ("signal", "key", "words"),
    [
        (ProxySignal.UNTRUSTED_FORWARDING, UNTRUSTED, "forwarding headers"),
        (ProxySignal.ORIGIN_MISMATCH, MISMATCH, "origin differs"),
        (
            ProxySignal.PUBLIC_ORIGIN_MISMATCH,
            PUBLIC_MISMATCH,
            "MENAGERIST_API_PUBLIC_ORIGIN",
        ),
        (ProxySignal.INSECURE_ORIGIN, INSECURE, "plain http"),
    ],
)
async def test_warns_with_a_hint_for_each_signal(
    signal: ProxySignal, key: str, words: str
) -> None:
    """A signal warns on its own row, naming the setting to look at."""
    proxy_signals.record(signal)

    result = await ProxyConfigurationCheck().run()

    obs = result[key]
    assert obs.status is CheckStatus.WARN
    assert obs.observed_value == 1
    assert obs.output is not None
    assert words in obs.output
    assert "MENAGERIST_API_TRUSTED_PROXIES" in obs.output
    others = [o for k, o in result.items() if k != key]
    assert all(o.status is CheckStatus.PASS for o in others)


async def test_each_signal_keeps_its_own_count_and_hint() -> None:
    """Two signals give two warnings, not one merged row."""
    proxy_signals.record(ProxySignal.UNTRUSTED_FORWARDING)
    proxy_signals.record(ProxySignal.ORIGIN_MISMATCH)
    proxy_signals.record(ProxySignal.ORIGIN_MISMATCH)

    result = await ProxyConfigurationCheck().run()

    assert result[UNTRUSTED].observed_value == 1
    assert result[MISMATCH].observed_value == 2
    assert "forwarding headers" in (result[UNTRUSTED].output or "")
    assert "origin differs" in (result[MISMATCH].output or "")
