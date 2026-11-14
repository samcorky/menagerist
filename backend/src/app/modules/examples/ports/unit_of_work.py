from dataclasses import dataclass

from app.modules.transfer.ports.run_repository import RunRepository
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class ExampleRepos:
    """The examples module's repository bundle."""

    runs: RunRepository


ExampleUnitOfWork = UnitOfWork[ExampleRepos]
