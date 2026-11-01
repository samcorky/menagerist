"""Links between packs: what a pack may declare."""

import pytest

from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackItem,
    PackItemType,
    PackLink,
    PackRelationshipType,
)


def _pack(*links: PackLink, requires: tuple[str, ...] = ()) -> ExamplePack:
    return ExamplePack(
        id="music",
        requires=requires,
        relationship_types=(
            PackRelationshipType(ref="tie", slug="music-tie", label="Tie"),
        ),
        item_types=(PackItemType(ref="thing", slug="music-thing", label="Thing"),),
        items=(PackItem(ref="a", type_ref="thing", name="A"),),
        links=links,
    )


def _link(
    *,
    with_pack: str = "movies",
    source_ref: str = "a",
    target_ref: str = "movies:b",
    type_ref: str = "tie",
) -> PackLink:
    return PackLink(
        with_pack=with_pack,
        source_ref=source_ref,
        target_ref=target_ref,
        type_ref=type_ref,
    )


def test_a_valid_link_is_accepted_and_names_its_targets() -> None:
    """The pack reports who it links with and which of their items it needs."""
    pack = _pack(_link(), _link(target_ref="movies:c"))

    assert pack.link_targets == ("movies",)
    assert pack.link_item_refs() == {("movies", "b"), ("movies", "c")}


def test_the_other_pack_can_be_either_end() -> None:
    """Direction is free."""
    _pack(_link(source_ref="movies:b", target_ref="a"))


@pytest.mark.parametrize(
    ("overrides", "requires", "message"),
    [
        ({"with_pack": "music"}, (), "cannot link with itself"),
        ({"with_pack": "movies"}, ("movies",), "which it requires"),
        ({"with_pack": "Bad Id"}, (), "lowercase letters"),
        ({"source_ref": "nope"}, (), "unknown item 'nope'"),
        ({"target_ref": "games:b"}, (), "names pack 'games', not 'movies'"),
        (
            {"target_ref": "a", "source_ref": "a"},
            (),
            "must join an item of another pack",
        ),
        (
            {"source_ref": "movies:b", "target_ref": "movies:b"},
            (),
            "cannot join an item to itself",
        ),
        ({"type_ref": "movies:tie"}, (), "unknown type"),
        ({"type_ref": "missing"}, (), "unknown type"),
    ],
)
def test_a_bad_link_is_rejected(
    overrides: dict[str, str], requires: tuple[str, ...], message: str
) -> None:
    """Every rule in the spec's Pack format section is enforced."""
    with pytest.raises(InvalidPackError, match=message):
        _pack(_link(**overrides), requires=requires)


def test_a_pack_with_no_links_has_no_targets() -> None:
    """The default is no links."""
    pack = _pack()

    assert pack.link_targets == ()
    assert pack.link_item_refs() == frozenset()
