"""Tests for the Installation aggregate."""

import uuid

import pytest

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.modules.examples.domain.installation import (
    REMOVAL_ORDER,
    EntityKind,
    Installation,
    InstallationStatus,
    Outcome,
    adoptable_records,
)


def _started() -> Installation:
    return Installation.start("demo")


def _record(installation: Installation, ref: str = "a") -> uuid.UUID:
    entity_id = uuid.uuid7()
    installation.record(EntityKind.ITEM, ref, ref.upper(), entity_id, "hash")
    return entity_id


def test_start_creates_an_installing_installation() -> None:
    """A new installation is installing, active and empty."""
    installation = _started()
    assert installation.status is InstallationStatus.INSTALLING
    assert installation.is_active
    assert installation.entities == []


def test_record_adds_an_owned_entity_and_touches() -> None:
    """Recording adds an owned entity and bumps updated_at."""
    installation = _started()
    before = installation.updated_at
    entity_id = _record(installation)
    assert [r.entity_id for r in installation.owned()] == [entity_id]
    assert installation.updated_at >= before


def test_owned_can_be_filtered_by_kind() -> None:
    """Owned entities can be narrowed to one kind."""
    installation = _started()
    _record(installation)
    assert installation.owned(EntityKind.PRESET) == []
    assert len(installation.owned(EntityKind.ITEM)) == 1


def test_mark_installed_sets_the_time() -> None:
    """Marking installed sets the status and installed_at."""
    installation = _started()
    installation.mark_installed()
    assert installation.status is InstallationStatus.INSTALLED
    assert installation.installed_at is not None
    assert installation.is_active


def test_record_is_only_allowed_while_installing() -> None:
    """Recording after the install finished is rejected."""
    installation = _started()
    installation.mark_installed()
    with pytest.raises(InvalidInstallationStateError):
        _record(installation)


def test_mark_installed_twice_is_rejected() -> None:
    """An installed installation cannot be marked installed again."""
    installation = _started()
    installation.mark_installed()
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_installed()


def test_settle_marks_an_owned_entity_removed_or_kept() -> None:
    """Settling records the outcome and reason and stops ownership."""
    installation = _started()
    first = _record(installation, "a")
    second = _record(installation, "b")
    installation.settle(first, Outcome.REMOVED)
    installation.settle(second, Outcome.KEPT, "edited")
    kept = next(r for r in installation.entities if r.entity_id == second)
    assert kept.outcome is Outcome.KEPT
    assert kept.reason == "edited"
    assert installation.owned() == []


def test_settle_rejects_an_unknown_or_already_settled_entity() -> None:
    """Only currently owned entities can be settled."""
    installation = _started()
    entity_id = _record(installation)
    with pytest.raises(InvalidInstallationStateError):
        installation.settle(uuid.uuid7(), Outcome.REMOVED)
    installation.settle(entity_id, Outcome.REMOVED)
    with pytest.raises(InvalidInstallationStateError):
        installation.settle(entity_id, Outcome.REMOVED)


def test_settle_rejects_the_owned_outcome() -> None:
    """Settling cannot set the outcome back to owned."""
    installation = _started()
    entity_id = _record(installation)
    with pytest.raises(InvalidInstallationStateError):
        installation.settle(entity_id, Outcome.OWNED)


def test_mark_failed_needs_nothing_left_owned() -> None:
    """Failing is only allowed once every entity has been settled."""
    installation = _started()
    entity_id = _record(installation)
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_failed()
    installation.settle(entity_id, Outcome.REMOVED)
    installation.mark_failed()
    assert installation.status is InstallationStatus.FAILED
    assert not installation.is_active


def test_mark_removed_sets_the_time_when_nothing_is_owned() -> None:
    """Removing an empty installation sets status and removed_at."""
    installation = _started()
    installation.mark_installed()
    installation.mark_removed()
    assert installation.status is InstallationStatus.REMOVED
    assert installation.removed_at is not None


def test_mark_removed_is_rejected_while_something_is_owned() -> None:
    """Removal is blocked while the pack still owns an entity."""
    installation = _started()
    _record(installation)
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_removed()


def test_removed_and_failed_installations_cannot_change_again() -> None:
    """A failed installation accepts no further transitions."""
    installation = _started()
    installation.mark_failed()
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_installed()
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_removed()


def test_a_removed_installation_cannot_be_installed_or_failed() -> None:
    """A removed installation accepts neither mark_installed nor mark_failed."""
    installation = _started()
    installation.mark_installed()
    installation.mark_removed()
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_installed()
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_failed()


def test_an_installed_installation_cannot_be_failed() -> None:
    """Only an installing installation can fail."""
    installation = _started()
    installation.mark_installed()
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_failed()


def test_collection_is_a_kind_removed_between_connections_and_items() -> None:
    """Collections are removed after connections and before items."""
    assert EntityKind.COLLECTION.value == "collection"
    assert EntityKind("collection") is EntityKind.COLLECTION
    order = REMOVAL_ORDER
    assert order.index(EntityKind.CONNECTION) + 1 == order.index(EntityKind.COLLECTION)
    assert order.index(EntityKind.COLLECTION) + 1 == order.index(EntityKind.ITEM)
    assert set(order) == set(EntityKind)


def _closed(*records: tuple[EntityKind, str, Outcome]) -> Installation:
    """An installation whose entities were all settled as given."""
    installation = _started()
    for kind, ref, outcome in records:
        entity_id = uuid.uuid7()
        installation.record(kind, ref, ref, entity_id, "hash")
        if outcome is not Outcome.OWNED:
            installation.settle(entity_id, outcome)
    return installation


def test_a_kept_record_is_adoptable() -> None:
    """The only record for a (kind, ref) decides: kept means adoptable."""
    kept = _closed((EntityKind.ITEM, "a", Outcome.KEPT))
    removed = _closed((EntityKind.ITEM, "b", Outcome.REMOVED))

    found = adoptable_records([kept, removed])

    assert set(found) == {(EntityKind.ITEM, "a")}
    assert found[(EntityKind.ITEM, "a")] is kept.entities[0]


def test_a_newer_removal_supersedes_an_older_kept_record() -> None:
    """Newest first: a later removed (or owned) record hides an earlier kept one."""
    old = _closed(
        (EntityKind.ITEM, "a", Outcome.KEPT), (EntityKind.ITEM, "b", Outcome.KEPT)
    )
    new = _closed(
        (EntityKind.ITEM, "a", Outcome.REMOVED), (EntityKind.ITEM, "b", Outcome.OWNED)
    )

    assert adoptable_records([new, old]) == {}


def test_the_newest_kept_record_wins_over_older_rounds() -> None:
    """Two rounds that both kept the same thing resolve to the newer record."""
    old = _closed((EntityKind.ITEM, "a", Outcome.KEPT))
    new = _closed((EntityKind.ITEM, "a", Outcome.KEPT))

    found = adoptable_records([new, old])

    assert found[(EntityKind.ITEM, "a")] is new.entities[0]


def test_kinds_are_resolved_separately() -> None:
    """The same ref under another kind is a different entity."""
    old = _closed((EntityKind.ITEM_TYPE, "a", Outcome.KEPT))
    new = _closed((EntityKind.ITEM, "a", Outcome.REMOVED))

    assert set(adoptable_records([new, old])) == {(EntityKind.ITEM_TYPE, "a")}
