"""How an instance names and describes itself to the outside world."""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Branding:
    """The instance's name and description, as an administrator set them.

    Public: anything here may be shown to someone who is not signed in.
    """

    name: str = "Menagerist"
    short_name: str = "Menagerist"
    description: str
