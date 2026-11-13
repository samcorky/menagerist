import uuid

from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.domain.preset import Preset
from app.shared_kernel.content_filter import ContentFilter

OWNER = uuid.uuid7()
EVERYONE = ContentFilter.everyone()


async def test_add_and_get_round_trips() -> None:
    """A preset added to the repository can be retrieved by id."""
    repository = InMemoryPresetRepository()
    preset = Preset.create(
        owner_id=OWNER, kind="field", label="Condition", definition={}
    )

    await repository.add(preset)

    assert await repository.get(preset.id, scope=EVERYONE) is preset


async def test_get_returns_none_for_missing_or_deleted() -> None:
    """get() returns None for an unknown id and for a soft-deleted preset."""
    repository = InMemoryPresetRepository()
    preset = Preset.create(
        owner_id=OWNER, kind="field", label="Condition", definition={}
    )
    await repository.add(preset)

    assert await repository.get(uuid.uuid4(), scope=EVERYONE) is None

    preset.soft_delete()
    await repository.save(preset)
    assert await repository.get(preset.id, scope=EVERYONE) is None


async def test_list_orders_by_id_and_respects_after_and_limit() -> None:
    """list() returns non-deleted presets ordered by id, paginated."""
    repository = InMemoryPresetRepository()
    presets = [
        Preset.create(owner_id=OWNER, kind="field", label=f"P{i}", definition={})
        for i in range(3)
    ]
    gone = Preset.create(owner_id=OWNER, kind="field", label="Gone", definition={})
    gone.soft_delete()
    for p in [*presets, gone]:
        await repository.add(p)

    page = await repository.list(scope=EVERYONE, after=None, limit=2)
    assert [p.id for p in page] == sorted(p.id for p in presets)[:2]
    rest = await repository.list(scope=EVERYONE, after=page[-1].id, limit=10)
    assert [p.id for p in rest] == sorted(p.id for p in presets)[2:]


async def test_list_filters_by_kind() -> None:
    """list() can be scoped to one kind."""
    repository = InMemoryPresetRepository()
    field = Preset.create(
        owner_id=OWNER, kind="field", label="Condition", definition={}
    )
    choice_list = Preset.create(
        owner_id=OWNER, kind="choice_list", label="Grades", definition={}
    )
    await repository.add(field)
    await repository.add(choice_list)

    result = await repository.list(
        scope=EVERYONE, after=None, limit=10, kind="choice_list"
    )

    assert [p.id for p in result] == [choice_list.id]


async def test_list_filters_by_label_search_case_insensitively() -> None:
    """list() matches `q` against the label, ignoring case."""
    repository = InMemoryPresetRepository()
    match = Preset.create(
        owner_id=OWNER, kind="field", label="Condition Grade", definition={}
    )
    other = Preset.create(owner_id=OWNER, kind="field", label="Format", definition={})
    await repository.add(match)
    await repository.add(other)

    result = await repository.list(scope=EVERYONE, after=None, limit=10, q="condition")

    assert [p.id for p in result] == [match.id]


async def test_get_and_list_are_scoped_to_the_owner() -> None:
    """Another person's preset is neither fetched nor listed."""
    repository = InMemoryPresetRepository()
    mine = Preset.create(owner_id=OWNER, kind="field", label="Mine", definition={})
    theirs = Preset.create(
        owner_id=uuid.uuid7(), kind="field", label="Theirs", definition={}
    )
    await repository.add(mine)
    await repository.add(theirs)
    scope = ContentFilter.of(OWNER)

    assert await repository.get(mine.id, scope=scope) is mine
    assert await repository.get(theirs.id, scope=scope) is None
    assert await repository.list(scope=scope, after=None, limit=10) == [mine]


async def test_claim_orphaned_assigns_ownerless_and_legacy_rows() -> None:
    """Ownerless and legacy-owned presets move to the new owner; others stay."""
    repository = InMemoryPresetRepository()
    legacy_owner = uuid.uuid7()
    ownerless = Preset.create(owner_id=OWNER, kind="field", label="A", definition={})
    ownerless.owner_id = None
    legacy = Preset.create(
        owner_id=legacy_owner, kind="field", label="B", definition={}
    )
    other = Preset.create(owner_id=uuid.uuid7(), kind="field", label="C", definition={})
    for preset in (ownerless, legacy, other):
        await repository.add(preset)
    new_owner = uuid.uuid7()

    claimed = await repository.claim_orphaned(
        new_owner, legacy_owner_ids=frozenset({legacy_owner})
    )

    assert claimed == 2
    assert ownerless.owner_id == legacy.owner_id == new_owner
    assert other.owner_id != new_owner
