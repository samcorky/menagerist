from dataclasses import dataclass

from app.modules.graph.ports.external_conditions import ExternalConditions
from app.shared_kernel.content_filter import ContentFilter


@dataclass(frozen=True, kw_only=True)
class QueryEnv:
    """What a leaf needs beyond the item: the scope and the external data source.

    With no `external`, media and manual-collection conditions match nothing.
    """

    scope: ContentFilter
    external: ExternalConditions | None = None
