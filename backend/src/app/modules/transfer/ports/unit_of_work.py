from dataclasses import dataclass

from app.modules.transfer.ports.source_link_repository import SourceLinkRepository
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class TransferRepos:
    """The transfer module's repository bundle."""

    links: SourceLinkRepository


TransferUnitOfWork = UnitOfWork[TransferRepos]
