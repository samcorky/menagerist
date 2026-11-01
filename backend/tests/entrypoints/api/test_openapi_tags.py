"""The documented tag groups: every used tag declared, System and v1 last."""

from app.entrypoints.api import create_app


def _declared_and_used() -> tuple[list[str], set[str]]:
    schema = create_app().openapi()
    used = {
        tag
        for item in schema["paths"].values()
        for operation in item.values()
        for tag in operation.get("tags", [])
    }
    return [tag["name"] for tag in schema["tags"]], used


def test_every_tag_a_route_uses_is_declared() -> None:
    """An undeclared tag would sort after the declared groups."""
    declared, used = _declared_and_used()
    assert used - set(declared) == set()


def test_system_then_v1_come_last() -> None:
    """The version group is the last tag, preceded by System."""
    declared, _ = _declared_and_used()
    assert declared[-2:] == ["System", "v1"]
