from app.shared_kernel.text import fold


def test_fold_ignores_case_and_accents() -> None:
    """Folding drops case and accents."""
    assert fold("CAFÉ") == fold("cafe") == "cafe"
