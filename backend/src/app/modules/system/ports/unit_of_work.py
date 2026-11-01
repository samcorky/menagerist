"""The system repository bundle and its shared transaction boundary."""

from dataclasses import dataclass

from app.modules.system.ports.update_check_store import UpdateCheckStore
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class SystemRepos:
    """Repositories participating in one system transaction."""

    updates: UpdateCheckStore


SystemUnitOfWork = UnitOfWork[SystemRepos]
