from dataclasses import dataclass


@dataclass(frozen=True)
class DefinitionWarning:
    """A part of a definition that no longer applies, such as a removed field."""

    path: str
    message: str
