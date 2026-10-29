from datetime import UTC, datetime, timedelta

import pytest

from app.modules.system.domain.release import (
    CheckFailure,
    Release,
    ReleaseChannel,
    ReleaseStatus,
    UpdateCheck,
    UpdateStatus,
    assess,
    parse_github_repository,
    select_latest,
)

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def release(version: str, *, prerelease: bool = False) -> Release:
    """Release."""
    return Release(
        version=version,
        url=f"https://github.com/o/r/releases/tag/{version}",
        prerelease=prerelease,
    )


def check(latest: Release | None, *, success: bool = True) -> UpdateCheck:
    """Check."""
    return UpdateCheck(
        source="o/r",
        channel=ReleaseChannel.STABLE,
        latest=latest,
        last_success_at=NOW if success else None,
        last_attempt_at=NOW,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/samcorky/menagerist",
        "https://github.com/samcorky/menagerist/",
        "https://github.com/samcorky/menagerist.git",
        " https://github.com/samcorky/menagerist ",
    ],
)
def test_a_github_repository_url_is_recognised(url: str) -> None:
    """A github repository url is recognised."""
    repository = parse_github_repository(url)

    assert repository is not None
    assert repository.slug == "samcorky/menagerist"
    assert repository.url == "https://github.com/samcorky/menagerist"


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "http://github.com/o/r",
        "https://gitlab.com/o/r",
        "https://github.com.evil.example/o/r",
        "https://github.com/o",
        "https://github.com/o/r/extra",
        "https://github.com/o/..",
        "https://github.com/-o/r",
        "https://user@github.com/o/r",
        "https://github.com/o/r?x=1",
    ],
)
def test_any_other_url_is_refused(url: str | None) -> None:
    """Only github.com/owner/name is ever fetched."""
    assert parse_github_repository(url) is None


def test_stable_skips_prereleases_and_unreadable_tags() -> None:
    """Stable skips prereleases and unreadable tags."""
    candidates = [
        release("0.2026.12.0rc1", prerelease=True),
        release("0.2026.11.0"),
        release("latest"),
        release("0.2026.10.0"),
    ]

    chosen = select_latest(candidates, ReleaseChannel.STABLE)

    assert chosen is not None
    assert chosen.version == "0.2026.11.0"


def test_a_prerelease_flag_or_a_prerelease_tag_both_exclude_from_stable() -> None:
    """A prerelease flag or a prerelease tag both exclude from stable."""
    flagged = release("0.2026.12.0", prerelease=True)
    tagged = release("0.2026.12.0rc1")

    assert select_latest([flagged, tagged], ReleaseChannel.STABLE) is None


def test_preview_takes_the_highest_version_even_when_a_final_follows_a_candidate() -> (
    None
):
    """Preview takes the highest version even when a final follows a candidate."""
    candidates = [
        release("0.2026.12.0rc1", prerelease=True),
        release("0.2026.12.0"),
        release("0.2026.11.0"),
    ]

    chosen = select_latest(candidates, ReleaseChannel.PREVIEW)

    assert chosen is not None
    assert chosen.version == "0.2026.12.0"


def test_the_highest_version_wins_over_the_newest_publication() -> None:
    """A backport published last is not the latest release."""
    candidates = [release("0.2026.10.5"), release("0.2026.11.0")]

    chosen = select_latest(reversed(candidates), ReleaseChannel.STABLE)

    assert chosen is not None
    assert chosen.version == "0.2026.11.0"


def test_nothing_eligible_selects_nothing() -> None:
    """Nothing eligible selects nothing."""
    assert select_latest([], ReleaseChannel.STABLE) is None


@pytest.mark.parametrize(
    ("installed", "latest", "expected"),
    [
        ("0.2026.10.0", "0.2026.11.0", UpdateStatus.UPDATE_AVAILABLE),
        ("0.2026.11.0", "v0.2026.11.0", UpdateStatus.UP_TO_DATE),
        ("0.2026.12.0", "0.2026.11.0", UpdateStatus.AHEAD),
        ("0.2026.10.0.dev187", "0.2026.11.0", UpdateStatus.DEVELOPMENT),
        ("not-a-version", "0.2026.11.0", UpdateStatus.UNKNOWN),
    ],
)
def test_the_installed_build_is_compared_with_the_latest(
    installed: str, latest: str, expected: UpdateStatus
) -> None:
    """The installed build is compared with the latest."""
    assert assess(installed, dirty=False, check=check(release(latest))) is expected


def test_an_uncommitted_build_is_never_called_out_of_date() -> None:
    """An uncommitted build is never called out of date."""
    result = assess("0.2026.10.0", dirty=True, check=check(release("0.2026.11.0")))

    assert result is UpdateStatus.DEVELOPMENT


def test_never_checked_is_unknown_not_up_to_date() -> None:
    """Never checked is unknown not up to date."""
    assert assess("1.0.0", dirty=False, check=None) is UpdateStatus.UNKNOWN
    unsuccessful = check(None, success=False)
    assert assess("1.0.0", dirty=False, check=unsuccessful) is UpdateStatus.UNKNOWN


def test_a_source_with_no_eligible_release_is_not_up_to_date() -> None:
    """A source with no eligible release is not up to date."""
    assert assess("1.0.0", dirty=False, check=check(None)) is UpdateStatus.NO_RELEASE


def test_an_unreadable_stored_version_is_unknown() -> None:
    """An unreadable stored version is unknown."""
    result = assess("1.0.0", dirty=False, check=check(release("nightly")))

    assert result is UpdateStatus.UNKNOWN


def test_a_failed_attempt_keeps_the_last_good_answer() -> None:
    """A failed attempt keeps the last good answer."""
    earlier = NOW - timedelta(days=1)
    good = UpdateCheck(
        source="o/r",
        channel=ReleaseChannel.STABLE,
        latest=release("0.2026.11.0"),
        last_success_at=earlier,
        last_attempt_at=earlier,
    )

    failed = good.failed(CheckFailure.TIMEOUT, at=NOW)

    assert failed.latest == good.latest
    assert failed.last_success_at == earlier
    assert failed.last_attempt_at == NOW
    assert failed.failure is CheckFailure.TIMEOUT
    assert failed.succeeded(latest=good.latest, at=NOW).failure is None


def test_a_check_is_recent_for_a_minute() -> None:
    """A check is recent for a minute."""
    recent = check(None)

    assert recent.is_recent(NOW + timedelta(seconds=59))
    assert not recent.is_recent(NOW + timedelta(minutes=1))


def test_the_status_reports_what_is_known_and_what_is_not() -> None:
    """The status reports what is known and what is not."""
    known = ReleaseStatus.of(
        installed="0.2026.10.0",
        dirty=False,
        channel=ReleaseChannel.STABLE,
        check=check(release("0.2026.11.0")),
    )
    unchecked = ReleaseStatus.of(
        installed="0.2026.10.0", dirty=False, channel=ReleaseChannel.PREVIEW, check=None
    )

    assert known.status is UpdateStatus.UPDATE_AVAILABLE
    assert known.checked_at == NOW
    assert unchecked.status is UpdateStatus.UNKNOWN
    assert unchecked.latest is None
    assert unchecked.checked_at is None
    assert unchecked.last_attempt_at is None
    assert unchecked.channel is ReleaseChannel.PREVIEW


def test_the_storage_key_separates_repositories_and_channels() -> None:
    """The storage key separates repositories and channels."""
    repository = parse_github_repository("https://github.com/o/r")
    other = parse_github_repository("https://github.com/o/other")
    assert repository is not None
    assert other is not None

    keys = {
        UpdateCheck.key(repository, ReleaseChannel.STABLE),
        UpdateCheck.key(repository, ReleaseChannel.PREVIEW),
        UpdateCheck.key(other, ReleaseChannel.STABLE),
    }

    assert len(keys) == 3
