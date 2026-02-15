"""Store-related Pydantic models for Agent Protocol"""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class StorePutRequest(BaseModel):
    """Request model for storing items"""

    namespace: list[str] = Field(..., description="Storage namespace")
    key: str = Field(..., description="Item key")
    value: dict[str, Any] = Field(..., description="Item value (must be a JSON object)")

    @field_validator("value", mode="before")
    @classmethod
    def validate_value_is_dict(cls, v: Any) -> dict[str, Any]:
        """Validate that value is a dictionary.

        LangGraph store requires values to be dictionaries for proper
        serialization and search functionality.
        """
        if not isinstance(v, dict):
            raise ValueError(f"Value must be a dictionary (JSON object), got {type(v).__name__}")
        return v


class StoreGetResponse(BaseModel):
    """Response model for getting items"""

    key: str
    value: Any
    namespace: list[str]


class StoreSearchRequest(BaseModel):
    """Request model for searching store items"""

    namespace_prefix: list[str] = Field(..., description="Namespace prefix to search")
    filter: dict[str, Any] | None = Field(None, description="Optional dictionary of key-value pairs to filter results.")
    query: str | None = Field(None, description="Search query")
    limit: int | None = Field(20, le=100, ge=1, description="Maximum results")
    offset: int | None = Field(0, ge=0, description="Results offset")


class StoreItem(BaseModel):
    """Store item model"""

    key: str
    value: Any
    namespace: list[str]


class StoreSearchResponse(BaseModel):
    """Response model for store search"""

    items: list[StoreItem]
    total: int
    limit: int
    offset: int


class StoreDeleteRequest(BaseModel):
    """Request body for deleting store items (SDK-compatible)."""

    namespace: list[str]
    key: str


class StoreListNamespacesRequest(BaseModel):
    """Request model for listing store namespaces"""

    prefix: list[str] | None = Field(None, description="Filter by namespace prefix")
    suffix: list[str] | None = Field(None, description="Filter by namespace suffix")
    max_depth: int | None = Field(None, le=100, ge=1, description="Maximum namespace depth to return")
    limit: int = Field(100, le=1000, ge=1, description="Maximum results")
    offset: int = Field(0, ge=0, description="Results offset")


class StoreListNamespacesResponse(BaseModel):
    """Response model for listing store namespaces"""

    namespaces: list[list[str]]
