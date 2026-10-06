import json
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.examples.domain.errors import InvalidPackError

if TYPE_CHECKING:
    from pathlib import Path

_ENTRY = {"id": "demo", "name": "Demo", "description": "A demo"}


def _write(
    root: Path, index: list[dict[str, str]], packs: dict[str, Any]
) -> FilePackCatalogue:
    (root / "index.json").write_text(
        json.dumps(
            {"format": "menagerist-examples-index", "version": 1, "packs": index}
        ),
        encoding="utf-8",
    )
    for name, data in packs.items():
        (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    return FilePackCatalogue(root)


async def test_lists_and_gets_packs(tmp_path: Path, pack_data: dict[str, Any]) -> None:
    """Packs listed in the index are summarised and retrievable."""
    catalogue = _write(tmp_path, [_ENTRY], {"demo": pack_data})

    summaries = await catalogue.list_packs()
    pack = await catalogue.get("demo")

    assert summaries[0].name == "Demo"
    assert summaries[0].counts.items == 2
    assert pack is not None
    assert pack.id == "demo"
    assert await catalogue.get("missing") is None


async def test_an_index_entry_without_a_file_is_rejected(tmp_path: Path) -> None:
    """An index entry with no pack file raises `InvalidPackError`."""
    catalogue = _write(tmp_path, [_ENTRY], {})

    with pytest.raises(InvalidPackError):
        await catalogue.list_packs()


async def test_a_missing_index_is_rejected(tmp_path: Path) -> None:
    """A missing `index.json` raises `InvalidPackError`."""
    with pytest.raises(InvalidPackError):
        await FilePackCatalogue(tmp_path).list_packs()


async def test_a_file_whose_id_differs_from_its_name_is_rejected(
    tmp_path: Path, pack_data: dict[str, Any]
) -> None:
    """A pack declaring a different id from its file name is rejected."""
    catalogue = _write(tmp_path, [_ENTRY], {"demo": {**pack_data, "id": "other"}})

    with pytest.raises(InvalidPackError):
        await catalogue.get("demo")


async def test_unreadable_json_is_an_invalid_pack_error(tmp_path: Path) -> None:
    """Invalid JSON raises `InvalidPackError`, not a bare decode error."""
    catalogue = _write(tmp_path, [_ENTRY], {})
    (tmp_path / "demo.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(InvalidPackError):
        await catalogue.get("demo")


async def test_a_pack_is_parsed_once(tmp_path: Path, pack_data: dict[str, Any]) -> None:
    """A pack is cached after its first load."""
    catalogue = _write(tmp_path, [_ENTRY], {"demo": pack_data})
    first = await catalogue.get("demo")

    (tmp_path / "demo.json").unlink()

    assert await catalogue.get("demo") is first


async def test_defaults_to_the_packaged_directory() -> None:
    """Without a root, the packs shipped inside the module are listed."""
    packs = await FilePackCatalogue().list_packs()

    assert packs
    assert all(p.counts.items > 0 for p in packs)


async def test_an_unsafe_index_id_never_reads_outside_the_directory(
    tmp_path: Path, pack_data: dict[str, Any]
) -> None:
    """A traversal id is rejected without reading the sentinel above the root."""
    root = tmp_path / "examples"
    root.mkdir()
    (tmp_path / "outside.json").write_text(
        json.dumps({**pack_data, "id": "outside"}), encoding="utf-8"
    )
    entry = {"id": "../outside", "name": "n", "description": "d"}
    catalogue = _write(root, [entry], {})

    with pytest.raises(InvalidPackError):
        await catalogue.get("../outside")
    with pytest.raises(InvalidPackError):
        await catalogue.list_packs()


async def test_an_id_missing_from_the_index_is_none_without_file_access(
    tmp_path: Path,
) -> None:
    """Unlisted ids, however odd, return `None`."""
    catalogue = _write(tmp_path, [], {})

    assert await catalogue.get("../x") is None
    assert await catalogue.get("a/b") is None


async def test_a_pack_file_resolving_outside_the_directory_is_rejected(
    tmp_path: Path, pack_data: dict[str, Any]
) -> None:
    """A symlink leading out of the directory is refused."""
    root = tmp_path / "examples"
    root.mkdir()
    (tmp_path / "real.json").write_text(json.dumps(pack_data), encoding="utf-8")
    catalogue = _write(root, [_ENTRY], {})
    (root / "demo.json").symlink_to(tmp_path / "real.json")

    with pytest.raises(InvalidPackError):
        await catalogue.get("demo")


async def test_deeply_nested_json_is_an_invalid_pack_error(tmp_path: Path) -> None:
    """Pathological nesting raises `InvalidPackError`, not `RecursionError`."""
    catalogue = _write(tmp_path, [_ENTRY], {})
    (tmp_path / "demo.json").write_text("[" * 100000, encoding="utf-8")

    with pytest.raises(InvalidPackError):
        await catalogue.get("demo")


@pytest.mark.parametrize("pack_id", ["../x", "A_B", "a/b", ""])
def test_load_refuses_an_unsafe_id_before_reading_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pack_id: str
) -> None:
    """The guard in `_load` fires on its own, with no file read."""
    catalogue = FilePackCatalogue(tmp_path)

    def read(name: str) -> Any:  # noqa: ANN401
        raise AssertionError(f"read {name}")

    monkeypatch.setattr(catalogue, "_read", read)

    with pytest.raises(InvalidPackError, match="outside the examples directory"):
        catalogue._load(pack_id)


def test_load_refuses_an_escaping_path_before_reading_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pack_data: dict[str, Any]
) -> None:
    """A symlink out of the directory is refused by `_load` with no file read."""
    root = tmp_path / "examples"
    root.mkdir()
    (tmp_path / "real.json").write_text(json.dumps(pack_data), encoding="utf-8")
    (root / "demo.json").symlink_to(tmp_path / "real.json")
    catalogue = FilePackCatalogue(root)

    def read(name: str) -> Any:  # noqa: ANN401
        raise AssertionError(f"read {name}")

    monkeypatch.setattr(catalogue, "_read", read)

    with pytest.raises(InvalidPackError, match="outside the examples directory"):
        catalogue._load("demo")
