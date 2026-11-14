import pytest

from app.modules.catalogue.domain.entry import CatalogueEntry, EntrySection
from app.modules.catalogue.domain.errors import InvalidEntryError
from app.modules.transfer.domain.bundle import PackItemType, PackPreset

_PRESET = PackPreset(ref="preset-1", kind="choice_list", label="L", definition={})
_TYPE = PackItemType(ref="person", slug="person", label="Person")


def _entry(**kwargs: object) -> CatalogueEntry:
    return CatalogueEntry(
        id="x",
        title="X",
        description="d",
        section=EntrySection.FIELD,
        **kwargs,  # type: ignore[arg-type]
    )


def test_an_entry_needs_something_to_install() -> None:
    """An entry needs something to install."""
    with pytest.raises(InvalidEntryError):
        _entry()


def test_an_entry_cannot_mix_presets_with_types() -> None:
    """An entry cannot mix presets with types."""
    with pytest.raises(InvalidEntryError):
        _entry(presets=(_PRESET,), item_types=(_TYPE,))


def test_a_preset_entry_and_a_type_entry_are_valid() -> None:
    """A preset entry and a type entry are valid."""
    assert _entry(presets=(_PRESET,)).presets == (_PRESET,)
    assert _entry(item_types=(_TYPE,)).item_types == (_TYPE,)
