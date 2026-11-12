from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.search.domain.search_hit import SearchHit, SearchKind, SearchOutcome


class SearchHitResponse(BaseModel):
    """One thing the search found."""

    kind: SearchKind
    ref: str = Field(
        description="An id (item, collection), slug (item type) or key (setting, task)."
    )
    title: str = Field(description="What it is called, as shown in the results.")
    description: str | None = Field(
        default=None, description="What it is or does, when the owner has said."
    )
    group: str | None = Field(
        default=None, description="An item's type slug, or a setting's section."
    )
    slug: str | None = Field(default=None, description="A collection's address.")
    item_count: int | None = Field(
        default=None, description="How many items a collection holds."
    )
    attributes: dict[str, Any] | None = Field(
        default=None, description="An item's field values."
    )
    score: int = Field(description="How well it matches; higher is better.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "kind": "setting",
                    "ref": "backup.keep_last",
                    "title": "Backups to keep",
                    "description": "Minimum number of ordinary backups to retain.",
                    "group": "backup",
                    "score": 80,
                }
            ]
        }
    )

    @classmethod
    def from_domain(cls, hit: SearchHit) -> SearchHitResponse:
        """Build the response from a hit."""
        return cls(**hit.__dict__)


class SearchResponse(BaseModel):
    """Everything found, best first, and the kinds that could not be searched."""

    results: list[SearchHitResponse] = Field(
        description="Everything found across the kinds, best match first."
    )
    failed: list[SearchKind] = Field(
        description="Kinds whose search failed; the other results are still valid."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "results": [
                        {
                            "kind": "item_type",
                            "ref": "film",
                            "title": "Film",
                            "score": 100,
                        }
                    ],
                    "failed": [],
                }
            ]
        }
    )

    @classmethod
    def from_domain(cls, outcome: SearchOutcome) -> SearchResponse:
        """Build the response from a search outcome."""
        return cls(
            results=[SearchHitResponse.from_domain(h) for h in outcome.hits],
            failed=outcome.failed,
        )
