"""Parsing and validating `links`."""

from typing import Any

import pytest

from app.modules.examples.adapters.platform.in_memory_pack_catalogue import (
    InMemoryPackCatalogue,
)
from app.modules.examples.adapters.platform.pack_parser import parse_pack
from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackItem,
    PackItemType,
    PackLink,
    PackRelationshipType,
)


def _doc(version: int = 5, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "format": "menagerist-example-pack",
        "version": version,
        "id": "music",
        "relationship_types": [{"ref": "tie", "slug": "music-tie", "label": "Tie"}],
        "item_types": [{"ref": "thing", "slug": "music-thing", "label": "Thing"}],
        "items": [{"ref": "a", "type": "thing", "name": "A"}],
        **extra,
    }


_LINK = {"with": "movies", "from": "a", "to": "movies:b", "type": "tie"}


def test_a_version_5_pack_may_declare_links() -> None:
    """`links` parse into `PackLink`s."""
    pack = parse_pack(_doc(links=[{**_LINK, "attributes": {"n": 1}}]))

    [link] = pack.links
    assert (link.with_pack, link.source_ref, link.target_ref, link.type_ref) == (
        "movies",
        "a",
        "movies:b",
        "tie",
    )
    assert link.attributes == {"n": 1}


def test_links_need_version_5() -> None:
    """Older versions do not know the key."""
    with pytest.raises(InvalidPackError, match="links"):
        parse_pack(_doc(version=4, links=[_LINK]))


@pytest.mark.parametrize("missing", ["with", "from", "to", "type"])
def test_a_link_needs_its_four_keys(missing: str) -> None:
    """Required keys are enforced."""
    link = {k: v for k, v in _LINK.items() if k != missing}
    with pytest.raises(InvalidPackError):
        parse_pack(_doc(links=[link]))


def test_a_link_rejects_unknown_keys() -> None:
    """Strict like the rest of the format."""
    with pytest.raises(InvalidPackError):
        parse_pack(_doc(links=[{**_LINK, "colour": "red"}]))


def _movies() -> ExamplePack:
    return ExamplePack(
        id="movies",
        item_types=(PackItemType(ref="film", slug="movies-film", label="Film"),),
        items=(PackItem(ref="b", type_ref="film", name="B"),),
    )


def _music(target: str = "movies:b") -> ExamplePack:
    return ExamplePack(
        id="music",
        relationship_types=(
            PackRelationshipType(ref="tie", slug="music-tie", label="Tie"),
        ),
        item_types=(PackItemType(ref="thing", slug="music-thing", label="Thing"),),
        items=(PackItem(ref="a", type_ref="thing", name="A"),),
        links=(
            PackLink(
                with_pack="movies", source_ref="a", target_ref=target, type_ref="tie"
            ),
        ),
    )


async def test_the_catalogue_accepts_links_and_reports_them() -> None:
    """Summaries say who each pack links with."""
    catalogue = InMemoryPackCatalogue()
    catalogue.add(_movies(), name="Movies", description="d")
    catalogue.add(_music(), name="Music", description="d")

    summaries = {s.id: s for s in await catalogue.list_packs()}

    assert summaries["music"].links_with == ("movies",)
    assert summaries["movies"].links_with == ()


def test_the_catalogue_rejects_a_link_to_a_missing_pack() -> None:
    """`with` must be a pack the catalogue has."""
    catalogue = InMemoryPackCatalogue()

    with pytest.raises(InvalidPackError, match="links with movies"):
        catalogue.add(_music(), name="Music", description="d")


def test_the_catalogue_rejects_a_link_to_an_item_the_other_pack_lacks() -> None:
    """The other end must exist in the other pack's file."""
    catalogue = InMemoryPackCatalogue()
    catalogue.add(_movies(), name="Movies", description="d")

    with pytest.raises(InvalidPackError, match="movies:nope"):
        catalogue.add(_music(target="movies:nope"), name="Music", description="d")
