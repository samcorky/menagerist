# /// script
# requires-python = ">=3.14"
# dependencies = ["pycountry==26.2.16"]
# ///
"""Regenerate the ISO 3166-1 countries and ISO 4217 currencies data files.

Run from the repo root with `poe generate-iso-data` (or `uv run --script
scripts/generate_iso_data.py`). Writes `shared/iso-data.json`, which the backend seed
migration and the frontend currency picker both read. The Dockerfile copies `shared/`
into both images, so there is only one copy in the repository.
"""

import json
from pathlib import Path
from typing import Any

import pycountry

# Fictional currencies with app-local codes, not ISO 4217. Codes must not start with X.
FICTIONAL_CURRENCIES = [
    ("GPL", "Gold-Pressed Latinum"),
    ("ZRU", "Hyrule Rupee"),
]

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = [ROOT / "shared/iso-data.json"]


def _get_countries() -> list[dict[str, str]]:
    """Return the countries, sorted by code."""
    return sorted(
        (
            {"code": c.alpha_2, "alpha3": c.alpha_3, "name": c.name}
            for c in pycountry.countries
        ),
        key=lambda c: c["code"],
    )


def _get_currencies() -> list[dict[str, str]]:
    """Return the currencies, sorted by code."""
    for code, name in FICTIONAL_CURRENCIES:
        pycountry.currencies.add_entry(alpha_3=code, name=name)  # type: ignore[no-untyped-call]
    # ISO 4217 reserves X codes for metals, funds and testing, not national money.
    return sorted(
        (
            {"code": c.alpha_3, "name": c.name}
            for c in pycountry.currencies
            if not c.alpha_3.startswith("X")
        ),
        key=lambda c: c["code"],
    )


def build() -> dict[str, Any]:
    """Return the countries and currencies, sorted by code."""
    countries = _get_countries()
    currencies = _get_currencies()
    return {"countries": countries, "currencies": currencies}


def main() -> None:
    """Write the generated JSON to every output path."""
    text = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    for path in OUTPUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
