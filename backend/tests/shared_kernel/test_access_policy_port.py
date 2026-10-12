from app.shared_kernel.access_policy import AccessPolicy

EXPECTED = {
    "scope_for",
    "assert_can_view",
    "assert_can_modify",
    "assert_can_delete",
}


def test_access_policy_protocol_exposes_the_decision_methods() -> None:
    """The port names exactly the questions use cases may ask."""
    assert {n for n in vars(AccessPolicy) if not n.startswith("_")} == EXPECTED
