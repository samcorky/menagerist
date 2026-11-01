"""The item type colour palette is the same list on the backend and the frontend."""

import json

from app.modules.graph.domain.node_type import TYPE_COLOURS
from app.platform.shared_data import shared_data_path


def test_the_palette_matches_the_shared_contract() -> None:
    """The backend palette is exactly the shared contract, in order."""
    contract = json.loads(
        shared_data_path("contracts/type-colours.json").read_text(encoding="utf-8")
    )

    assert list(TYPE_COLOURS) == contract["colours"]
