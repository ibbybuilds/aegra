"""Error response models for Agent Protocol"""

from typing import Any

from pydantic import BaseModel, Field


class AgentProtocolError(BaseModel):
    """Standard Agent Protocol error response"""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(None, description="Additional error details")


def get_error_type(status_code: int) -> str:
    """Map HTTP status codes to error types"""
    error_map = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        500: "internal_error",
        501: "not_implemented",
        503: "service_unavailable",
    }
    return error_map.get(status_code, "unknown_error")
