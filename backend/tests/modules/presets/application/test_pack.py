import uuid

import pytest

from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.application.export_presets import (
    ExportPresets,
    ExportPresetsQuery,
)
from app.modules.presets.application.import_presets import (
    _PAGE_SIZE,
    ImportPresets,
    ImportPresetsCommand,
)
from app.modules.presets.application.pack import (
    MAX_DEFINITION_BYTES,
    MAX_PACK_ITEMS,
    content_hash,
)
from app.modules.presets.domain.errors import (
    InvalidPresetDefinitionError,
    PresetNotFoundError,
)
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

_GRADES = {"options": ["Mint", "Good"]}


def _item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "kind": "choice_list",
        "label": "Condition grades",
        "description": None,
        "definition": _GRADES,
    }
    item.update(overrides)
    return item


def _importer(repos: PresetRepos) -> ImportPresets:
    return ImportPresets(InMemoryUnitOfWork(repos))


async def test_import_creates_new_presets_with_fresh_ids() -> None:
    """Imported items become new, non-built-in presets."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    result = await _importer(repos).handle(
        ImportPresetsCommand(
            pack_format="menagerist-presets", pack_version=1, items=[_item()]
        ),
        SYSTEM_ACTOR,
    )

    assert (result.created, result.skipped) == (1, 0)
    stored = await repos.presets.list(after=None, limit=10)
    assert len(stored) == 1
    assert stored[0].builtin is False
    assert stored[0].label == "Condition grades"


async def test_import_skips_content_already_present() -> None:
    """Importing the same pack twice creates nothing the second time."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    command = ImportPresetsCommand(
        pack_format="menagerist-presets", pack_version=1, items=[_item(), _item()]
    )
    first = await _importer(repos).handle(command, SYSTEM_ACTOR)
    second = await _importer(repos).handle(command, SYSTEM_ACTOR)

    assert (first.created, first.skipped) == (1, 1)
    assert (second.created, second.skipped) == (0, 2)
    assert len(await repos.presets.list(after=None, limit=10)) == 1


async def test_import_rejects_the_whole_pack_when_one_item_is_bad() -> None:
    """A malformed item stops the pack before anything is stored."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    command = ImportPresetsCommand(
        pack_format="menagerist-presets",
        pack_version=1,
        items=[_item(), _item(kind="mystery")],
    )

    with pytest.raises(InvalidPresetDefinitionError):
        await _importer(repos).handle(command, SYSTEM_ACTOR)
    assert await repos.presets.list(after=None, limit=10) == []


@pytest.mark.parametrize(
    ("pack_format", "pack_version", "items"),
    [
        ("other-format", 1, []),
        ("menagerist-presets", 2, []),
        ("menagerist-presets", 1, [_item() for _ in range(MAX_PACK_ITEMS + 1)]),
    ],
)
async def test_import_rejects_bad_envelopes(
    pack_format: str, pack_version: int, items: list[dict[str, object]]
) -> None:
    """Unknown format, unknown version and oversized packs are refused."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    command = ImportPresetsCommand(
        pack_format=pack_format, pack_version=pack_version, items=items
    )

    with pytest.raises(InvalidPresetDefinitionError):
        await _importer(repos).handle(command, SYSTEM_ACTOR)


@pytest.mark.parametrize(
    "override",
    [
        {"label": "   "},
        {"label": "x" * 201},
        {"description": 5},
        {"definition": "not an object"},
        {"definition": {"options": ["x" * MAX_DEFINITION_BYTES]}},
    ],
)
async def test_import_rejects_bad_items(override: dict[str, object]) -> None:
    """Blank or oversized labels, bad descriptions and definitions are refused."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    command = ImportPresetsCommand(
        pack_format="menagerist-presets", pack_version=1, items=[_item(**override)]
    )

    with pytest.raises(InvalidPresetDefinitionError):
        await _importer(repos).handle(command, SYSTEM_ACTOR)


async def test_export_returns_presets_in_requested_order() -> None:
    """Export returns the requested presets in the order asked for."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    first = Preset.create(kind="choice_list", label="A", definition=_GRADES)
    second = Preset.create(kind="choice_list", label="B", definition=_GRADES)
    await repos.presets.add(first)
    await repos.presets.add(second)

    result = await ExportPresets(repos).handle(
        ExportPresetsQuery(ids=[second.id, first.id]), SYSTEM_ACTOR
    )

    assert [p.id for p in result] == [second.id, first.id]


async def test_export_rejects_a_missing_id() -> None:
    """An id that does not resolve to a live preset fails the export."""
    repos = PresetRepos(presets=InMemoryPresetRepository())

    with pytest.raises(PresetNotFoundError):
        await ExportPresets(repos).handle(
            ExportPresetsQuery(ids=[uuid.uuid7()]), SYSTEM_ACTOR
        )


def test_content_hash_ignores_key_order_but_not_content() -> None:
    """The hash is stable under key reordering and changes when content changes."""
    a = content_hash("choice_list", "A", {"options": ["x"], "z": 1})
    b = content_hash("choice_list", "A", {"z": 1, "options": ["x"]})
    c = content_hash("choice_list", "B", {"options": ["x"], "z": 1})

    assert a == b
    assert a != c


async def test_export_rejects_more_ids_than_a_pack_holds() -> None:
    """Asking for more presets than one pack may hold is refused before any lookup."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    ids = [uuid.uuid7() for _ in range(MAX_PACK_ITEMS + 1)]

    with pytest.raises(InvalidPresetDefinitionError):
        await ExportPresets(repos).handle(ExportPresetsQuery(ids=ids), SYSTEM_ACTOR)


async def test_import_detects_repeats_beyond_the_first_page() -> None:
    """A repeat is still skipped when the existing preset sits past the first page."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    for i in range(_PAGE_SIZE + 1):
        await repos.presets.add(
            Preset.create(kind="choice_list", label=f"L{i}", definition=_GRADES)
        )
    existing_label = f"L{_PAGE_SIZE}"

    result = await _importer(repos).handle(
        ImportPresetsCommand(
            pack_format="menagerist-presets",
            pack_version=1,
            items=[_item(label=existing_label, definition=_GRADES)],
        ),
        SYSTEM_ACTOR,
    )

    assert (result.created, result.skipped) == (0, 1)


async def test_import_reports_an_id_for_every_item_including_repeats() -> None:
    """Each item gets an id in pack order; repeats report the existing preset."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    existing = Preset.create(kind="choice_list", label="Grades", definition=_GRADES)
    await repos.presets.add(existing)

    result = await _importer(repos).handle(
        ImportPresetsCommand(
            pack_format="menagerist-presets",
            pack_version=1,
            items=[
                _item(label="Grades", definition=_GRADES),
                _item(label="Formats", definition={"options": ["LP"]}),
                _item(label="Formats", definition={"options": ["LP"]}),
            ],
        ),
        SYSTEM_ACTOR,
    )

    assert (result.created, result.skipped) == (1, 2)
    assert result.items[0].id == existing.id
    assert result.items[0].created is False
    assert result.items[1].created is True
    assert result.items[2].id == result.items[1].id
    assert result.items[2].created is False
    assert await repos.presets.get(result.items[1].id) is not None
