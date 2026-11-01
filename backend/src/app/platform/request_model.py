from pydantic import BaseModel, ConfigDict


class RequestModel(BaseModel):
    """Base for API request bodies. Unknown fields are rejected, not ignored."""

    model_config = ConfigDict(extra="forbid")
