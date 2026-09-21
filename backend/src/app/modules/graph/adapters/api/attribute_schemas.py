from pydantic import BaseModel, ConfigDict


class AttributeUsageResponse(BaseModel):
    """How many items (or connections) of a type hold a given attribute key."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"count": 12}]})

    count: int


class AttributePurgeResponse(BaseModel):
    """How many items (or connections) had an attribute key permanently removed."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"purged": 12}]})

    purged: int
