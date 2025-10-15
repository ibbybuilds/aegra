"""Store-related Pydantic models for Agent Protocol"""

from typing import Any

from pydantic import BaseModel, Field


class StorePutRequest(BaseModel):
    """Request model for storing items"""

    namespace: list[str] = Field(..., description="Storage namespace")
    key: str = Field(..., description="Item key")
    value: Any = Field(..., description="Item value")


class StoreGetResponse(BaseModel):
    """Response model for getting items"""

    key: str
    value: Any
    namespace: list[str]


class StoreSearchRequest(BaseModel):
    """Request model for searching store items"""

    namespace_prefix: list[str] = Field(..., description="Namespace prefix to search")
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
