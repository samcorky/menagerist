"""The `menagerist-bundle` file: Menagerist's own export and import format."""

from collections.abc import Mapping
from typing import Any

from app.modules.transfer.domain.bundle import (
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    REF_PATTERN,
    REF_RULE,
    Bundle,
    BundlePreset,
)
from app.modules.transfer.domain.errors import InvalidBundleError

_ENVELOPE = {"format", "version", "presets"}
_PRESET_REQUIRED = {"ref", "kind", "label", "definition"}
_PRESET_KEYS = _PRESET_REQUIRED | {"description"}


def _text(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise InvalidBundleError(f"{what} must be text")
    return value


def _preset(raw: object, n: int) -> BundlePreset:
    where = f"presets[{n}]"
    if not isinstance(raw, Mapping):
        raise InvalidBundleError(f"{where} must be an object")
    missing = _PRESET_REQUIRED - raw.keys()
    if missing:
        raise InvalidBundleError(f"{where} needs {', '.join(sorted(missing))}")
    unknown = raw.keys() - _PRESET_KEYS
    if unknown:
        raise InvalidBundleError(f"{where} has unknown keys {sorted(unknown)}")
    ref = _text(raw["ref"], f"{where} ref")
    if not REF_PATTERN.match(ref):
        raise InvalidBundleError(f"{where} ref {REF_RULE}")
    description = raw.get("description")
    if not isinstance(raw["definition"], dict):
        raise InvalidBundleError(f"{where} definition must be an object")
    return BundlePreset(
        ref=ref,
        kind=_text(raw["kind"], f"{where} kind"),
        label=_text(raw["label"], f"{where} label"),
        description=None
        if description is None
        else _text(description, f"{where} description"),
        definition=raw["definition"],
    )


class MenageristBundleCodec:
    """Reads and writes `menagerist-bundle` version 1, which holds presets.

    Only the file's shape is checked here; whether each preset is a valid one is
    the presets module's call, made when the bundle is planned.
    """

    format = BUNDLE_FORMAT

    def decode(self, data: Mapping[str, Any]) -> Bundle:
        """Read a parsed file into a bundle; unknown keys are refused.

        Raises:
            InvalidBundleError: the file is not a valid `menagerist-bundle`.
        """
        if data.get("version") != BUNDLE_VERSION:
            raise InvalidBundleError(
                f"unsupported {BUNDLE_FORMAT} version {data.get('version')!r}"
            )
        unknown = data.keys() - _ENVELOPE
        if unknown:
            raise InvalidBundleError(f"the file has unknown keys {sorted(unknown)}")
        presets = data.get("presets", [])
        if not isinstance(presets, list):
            raise InvalidBundleError("presets must be a list")
        return Bundle(
            id=BUNDLE_FORMAT,
            presets=tuple(_preset(raw, n) for n, raw in enumerate(presets)),
        )

    def encode(self, bundle: Bundle) -> dict[str, Any]:
        """Write `bundle` as a version 1 file."""
        return {
            "format": BUNDLE_FORMAT,
            "version": BUNDLE_VERSION,
            "presets": [
                {
                    "ref": p.ref,
                    "kind": p.kind,
                    "label": p.label,
                    "description": p.description,
                    "definition": p.definition,
                }
                for p in bundle.presets
            ],
        }
