import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.presets.adapters.persistence.preset_repository import (
    SqlAlchemyPresetRepository,
)
from app.modules.presets.domain.preset import Preset

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.paging import Cursor, PageRequest, SortOrder

OWNER = uuid.uuid7()
EVERYONE = ContentFilter.everyone()


pytestmark = pytest.mark.integration


def _fields(preset: Preset) -> tuple[object, ...]:
    return (
        preset.id,
        preset.kind,
        preset.label,
        preset.description,
        preset.definition,
        preset.version,
        preset.owner_id,
        preset.created_at,
        preset.updated_at,
        preset.deleted_at,
    )


async def test_add_and_get_round_trips(db_session: AsyncSession) -> None:
    """A preset added to the repository can be retrieved by id, fields intact."""
    repository = SqlAlchemyPresetRepository(db_session)
    preset = Preset.create(
        owner_id=OWNER,
        kind="field",
        label="Condition",
        description="A condition grade.",
        definition={"property": {"type": "string", "enum": ["Mint", "VG+"]}},
    )

    await repository.add(preset)
    result = await repository.get(preset.id, scope=EVERYONE)

    assert result is not None
    assert _fields(result) == _fields(preset)


async def test_get_returns_none_for_missing_preset(db_session: AsyncSession) -> None:
    """get() returns None for an id that was never added."""
    repository = SqlAlchemyPresetRepository(db_session)

    assert await repository.get(uuid.uuid4(), scope=EVERYONE) is None


async def test_get_returns_none_for_a_soft_deleted_preset(
    db_session: AsyncSession,
) -> None:
    """get() treats a soft-deleted preset as if it doesn't exist."""
    repository = SqlAlchemyPresetRepository(db_session)
    preset = Preset.create(
        owner_id=OWNER, kind="field", label="Condition", definition={}
    )
    await repository.add(preset)

    preset.soft_delete()
    await repository.save(preset)

    assert await repository.get(preset.id, scope=EVERYONE) is None


async def test_save_persists_a_version_bump(db_session: AsyncSession) -> None:
    """A definition change and its version bump survive a save/get round trip."""
    repository = SqlAlchemyPresetRepository(db_session)
    preset = Preset.create(
        owner_id=OWNER, kind="field", label="Condition", definition={"a": 1}
    )
    await repository.add(preset)

    preset.update(definition={"a": 2})
    await repository.save(preset)
    result = await repository.get(preset.id, scope=EVERYONE)

    assert result is not None
    assert result.definition == {"a": 2}
    assert result.version == 2


async def test_list_orders_by_id_ascending(db_session: AsyncSession) -> None:
    """list() returns presets ordered by id ascending, regardless of insert order."""
    repository = SqlAlchemyPresetRepository(db_session)
    presets = [
        Preset.create(owner_id=OWNER, kind="field", label=f"P{i}", definition={})
        for i in range(3)
    ]
    for preset in reversed(presets):
        await repository.add(preset)

    result = (await repository.list(scope=EVERYONE, page=PageRequest(limit=10))).items

    assert [p.id for p in result] == sorted(p.id for p in presets)


async def test_list_respects_after_and_limit(db_session: AsyncSession) -> None:
    """list() pages using `after` and `limit`."""
    repository = SqlAlchemyPresetRepository(db_session)
    presets = [
        Preset.create(owner_id=OWNER, kind="field", label=f"P{i}", definition={})
        for i in range(3)
    ]
    for preset in presets:
        await repository.add(preset)
    ordered = sorted(presets, key=lambda p: p.id)

    page = (await repository.list(scope=EVERYONE, page=PageRequest(limit=2))).items
    assert [p.id for p in page] == [p.id for p in ordered[:2]]

    rest = (
        await repository.list(
            scope=EVERYONE,
            page=PageRequest(after=Cursor.after_id(page[-1].id), limit=10),
        )
    ).items
    assert [p.id for p in rest] == [p.id for p in ordered[2:]]


async def test_list_filters_by_kind_and_label_search(db_session: AsyncSession) -> None:
    """list() can filter by `kind` and by a case-insensitive `q` on the label."""
    repository = SqlAlchemyPresetRepository(db_session)
    field = Preset.create(
        owner_id=OWNER, kind="field", label="Condition Grade", definition={}
    )
    choice_list = Preset.create(
        owner_id=OWNER, kind="choice_list", label="Condition List", definition={}
    )
    other = Preset.create(owner_id=OWNER, kind="field", label="Format", definition={})
    for preset in [field, choice_list, other]:
        await repository.add(preset)

    by_kind = (
        await repository.list(
            scope=EVERYONE, kind="choice_list", page=PageRequest(limit=10)
        )
    ).items
    assert [p.id for p in by_kind] == [choice_list.id]

    by_q = (
        await repository.list(scope=EVERYONE, q="condition", page=PageRequest(limit=10))
    ).items
    assert {p.id for p in by_q} == {field.id, choice_list.id}


async def test_list_excludes_soft_deleted_presets(db_session: AsyncSession) -> None:
    """A soft-deleted preset never appears in list()."""
    repository = SqlAlchemyPresetRepository(db_session)
    preset = Preset.create(
        owner_id=OWNER, kind="field", label="Condition", definition={}
    )
    await repository.add(preset)
    preset.soft_delete()
    await repository.save(preset)

    assert (
        await repository.list(scope=EVERYONE, page=PageRequest(limit=10))
    ).items == []


async def test_get_and_list_are_scoped_to_the_owner(db_session: AsyncSession) -> None:
    """Another person's preset is neither fetched nor listed."""
    repository = SqlAlchemyPresetRepository(db_session)
    mine = Preset.create(owner_id=OWNER, kind="field", label="Mine", definition={})
    theirs = Preset.create(
        owner_id=uuid.uuid7(), kind="field", label="Theirs", definition={}
    )
    await repository.add(mine)
    await repository.add(theirs)
    scope = ContentFilter.of(OWNER)

    assert await repository.get(theirs.id, scope=scope) is None
    fetched = await repository.get(mine.id, scope=scope)
    assert fetched is not None
    assert fetched.owner_id == OWNER
    assert [
        p.id
        for p in (await repository.list(scope=scope, page=PageRequest(limit=10))).items
    ] == [mine.id]


async def test_claim_orphaned_assigns_ownerless_and_legacy_rows(
    db_session: AsyncSession,
) -> None:
    """Ownerless and legacy-owned presets move to the new owner; others stay."""
    repository = SqlAlchemyPresetRepository(db_session)
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
    scope = ContentFilter.of(new_owner)
    assert await repository.get(ownerless.id, scope=scope) is not None
    assert await repository.get(legacy.id, scope=scope) is not None
    assert await repository.get(other.id, scope=scope) is None


def _preset(label: str, kind: str = "field") -> Preset:
    """A saved field with `label`, owned by `OWNER`."""
    return Preset.create(
        owner_id=OWNER,
        kind=kind,
        label=label,
        description=None,
        definition={"property": {"type": "string"}},
    )


async def test_list_sorts_by_label_ignoring_case_in_both_directions(
    db_session: AsyncSession,
) -> None:
    """`label` orders by `lower(label)`, and `desc` reverses it."""
    repository = SqlAlchemyPresetRepository(db_session)
    for label in ["banana", "Apple", "cherry", "apricot"]:
        await repository.add(_preset(label))

    ascending = await repository.list(scope=EVERYONE, page=PageRequest(sort="label"))
    descending = await repository.list(
        scope=EVERYONE, page=PageRequest(sort="label", order=SortOrder.DESC)
    )

    assert [p.label for p in ascending.items] == [
        "Apple",
        "apricot",
        "banana",
        "cherry",
    ]
    assert [p.label for p in descending.items] == [
        "cherry",
        "banana",
        "apricot",
        "Apple",
    ]


@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", [None, "label", "kind", "created_at", "updated_at"])
async def test_list_cursors_visit_every_row_once_in_order(
    db_session: AsyncSession, sort: str | None, order: SortOrder
) -> None:
    """Following `next` never repeats a preset or skips one."""
    repository = SqlAlchemyPresetRepository(db_session)
    for n, label in enumerate(["b", "A", "b", "c", "B", "a", "c"]):
        await repository.add(_preset(label, "choice_list" if n % 2 else "field"))
    everything = (
        await repository.list(
            scope=EVERYONE, page=PageRequest(sort=sort, order=order, limit=100)
        )
    ).items

    seen: list[uuid.UUID] = []
    request = PageRequest(sort=sort, order=order, limit=2)
    while True:
        page = await repository.list(scope=EVERYONE, page=request)
        seen.extend(p.id for p in page.items)
        if page.next is None:
            break
        request = PageRequest(after=page.next, sort=sort, order=order, limit=2)

    assert seen == [p.id for p in everything]
    assert len(set(seen)) == 7


async def test_list_q_ignores_accents_and_reads_wildcards_literally(
    db_session: AsyncSession,
) -> None:
    """`cafe` finds Café, and `%` or `_` only match themselves."""
    repository = SqlAlchemyPresetRepository(db_session)
    for label in ["Café au lait", "Tea", "50% off", "a_b", "axb"]:
        await repository.add(_preset(label))

    async def found(q: str) -> list[str]:
        page = await repository.list(scope=EVERYONE, page=PageRequest(), q=q)
        return [p.label for p in page.items]

    assert await found("CAFE") == ["Café au lait"]
    assert await found("50%") == ["50% off"]
    assert await found("a_b") == ["a_b"]
    assert await found("   ") == ["Café au lait", "Tea", "50% off", "a_b", "axb"]


async def test_list_q_matches_the_description_as_well_as_the_label(
    db_session: AsyncSession,
) -> None:
    """A preset is found by what its description says, ignoring accents."""
    repository = SqlAlchemyPresetRepository(db_session)
    described = Preset.create(
        owner_id=OWNER,
        kind="field",
        label="Grade",
        description="How the Café copy looks",
        definition={"property": {"type": "string"}},
    )
    await repository.add(described)
    await repository.add(_preset("Format"))

    page = await repository.list(scope=EVERYONE, page=PageRequest(), q="CAFE")

    assert [p.label for p in page.items] == ["Grade"]
