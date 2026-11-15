from typing import Any

import pytest

from app.modules.transfer.adapters.codecs.menagerist_bundle import MenageristBundleCodec
from app.modules.transfer.application.codecs import CodecRegistry
from app.modules.transfer.domain.bundle import Bundle, BundleItemType, BundlePreset
from app.modules.transfer.domain.errors import InvalidBundleError, UnknownFormatError

CODEC = MenageristBundleCodec()


def _preset(**change: object) -> dict[str, Any]:
    preset: dict[str, Any] = {
        "ref": "grades",
        "kind": "choice_list",
        "label": "Grades",
        "description": "Mint to poor.",
        "definition": {"options": ["Mint"]},
    }
    preset.update(change)
    return {k: v for k, v in preset.items() if v is not ...}


def _file(*presets: object, **change: object) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": "menagerist-bundle",
        "version": 1,
        "presets": list(presets),
    }
    data.update(change)
    return data


def test_a_file_decodes_and_encodes_back_the_same() -> None:
    """A file reads into a bundle of presets and writes back unchanged."""
    data = _file(_preset(), _preset(ref="other", description=None))

    bundle = CODEC.decode(data)

    assert bundle.id == "menagerist-bundle"
    assert [(p.ref, p.label, p.description) for p in bundle.presets] == [
        ("grades", "Grades", "Mint to poor."),
        ("other", "Grades", None),
    ]
    assert CODEC.encode(bundle) == data


def test_a_preset_may_leave_out_its_description() -> None:
    """`description` is optional."""
    bundle = CODEC.decode(_file(_preset(description=...)))
    assert bundle.presets[0].description is None


def test_a_file_without_presets_is_an_empty_bundle() -> None:
    """`presets` is optional."""
    assert CODEC.decode({"format": "menagerist-bundle", "version": 1}).presets == ()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_file(version=2), "unsupported menagerist-bundle version 2"),
        (_file(extra=1), "unknown keys"),
        (_file(presets={}), "presets must be a list"),
        (_file("text"), r"presets\[0\] must be an object"),
        (_file(_preset(kind=...)), "needs kind"),
        (_file(_preset(colour="red")), "unknown keys"),
        (_file(_preset(ref="Bad Ref")), "ref must be lowercase"),
        (_file(_preset(ref=5)), "ref must be text"),
        (_file(_preset(label=None)), "label must be text"),
        (_file(_preset(description=5)), "description must be text"),
        (_file(_preset(definition=[])), "definition must be an object"),
        (_file(_preset(), _preset()), "each preset needs its own ref"),
    ],
)
def test_a_malformed_file_is_refused(data: dict[str, Any], message: str) -> None:
    """A malformed file is refused with what is wrong."""
    with pytest.raises(InvalidBundleError, match=message):
        CODEC.decode(data)


def test_types_sharing_a_ref_are_refused() -> None:
    """Refs are unique within each kind of a bundle."""
    book = BundleItemType(ref="book", slug="book", label="Book")
    with pytest.raises(InvalidBundleError, match="each item type"):
        Bundle(id="b", item_types=(book, book))


def test_the_registry_finds_a_codec_by_format() -> None:
    """The registry returns the codec for a format, and refuses an unknown one."""
    registry = CodecRegistry([CODEC])

    assert registry.get("menagerist-bundle") is CODEC
    assert registry.formats == ("menagerist-bundle",)
    for unknown in ("menagerist-presets", None):
        with pytest.raises(UnknownFormatError, match="'menagerist-bundle'"):
            registry.get(unknown)


def test_two_codecs_for_one_format_are_a_mistake() -> None:
    """Registering one format twice fails at start-up."""
    with pytest.raises(ValueError, match="two codecs"):
        CodecRegistry([CODEC, MenageristBundleCodec()])


def test_a_bundle_preset_round_trips_through_encode() -> None:
    """Encoding writes every field of a preset."""
    preset = BundlePreset(ref="x", kind="field", label="X", definition={"a": 1})
    encoded = CODEC.encode(Bundle(id="b", presets=(preset,)))
    assert encoded["presets"] == [
        {
            "ref": "x",
            "kind": "field",
            "label": "X",
            "description": None,
            "definition": {"a": 1},
        }
    ]
