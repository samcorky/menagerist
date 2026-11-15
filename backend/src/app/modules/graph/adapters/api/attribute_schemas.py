from pydantic import BaseModel, ConfigDict, Field


class AttributeUsageResponse(BaseModel):
    """How many items (or connections) of a type hold a given attribute key."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"count": 12}]})

    count: int = Field(description="How many hold the field.")
