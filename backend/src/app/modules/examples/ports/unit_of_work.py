from dataclasses import dataclass

from app.modules.examples.ports.installation_repository import InstallationRepository
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class ExampleRepos:
    """The examples module's repository bundle."""

    installations: InstallationRepository


ExampleUnitOfWork = UnitOfWork[ExampleRepos]
