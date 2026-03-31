"""Assistant endpoints for Agent Protocol

NOTE: This API follows a layered architecture pattern with business logic
separated into a service layer (assistant_service.py). This was the first
API to be refactored, and the plan is to gradually refactor all other APIs
(runs, threads, etc.) to follow this same pattern for better code
organization, testability, and maintainability.

Architecture:
- API Layer (this file): Thin FastAPI route handlers, request/response handling
- Service Layer (assistant_service.py): Business logic, validation, orchestration
"""

from fastapi import APIRouter, Body, Depends, Query

from aegra_api.core.auth_deps import auth_dependency, get_current_user
from aegra_api.core.auth_handlers import build_auth_context, handle_event
from aegra_api.models import (
    AgentSchemas,
    Assistant,
    AssistantCreate,
    AssistantList,
    AssistantSearchRequest,
    AssistantUpdate,
    User,
)
from aegra_api.models.errors import NOT_FOUND
from aegra_api.services.assistant_service import AssistantService, get_assistant_service

router = APIRouter(tags=["Assistants"], dependencies=auth_dependency)


@router.post("/assistants", response_model=Assistant, response_model_by_alias=False)
async def create_assistant(
    request: AssistantCreate,
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Create a new assistant.

    An assistant is a configured instance of a graph. Provide a `graph_id`
    referencing a graph defined in your `aegra.json`. If `assistant_id` is
    omitted, one is auto-generated. Set `if_exists` to `"do_nothing"` for
    idempotent creation.
    """
    # Authorization check
    ctx = build_auth_context(user, "assistants", "create")
    value = request.model_dump()
    filters = await handle_event(ctx, value)

    # If handler modified metadata, update request
    if filters and "metadata" in filters:
        request.metadata = {**(request.metadata or {}), **filters["metadata"]}
    elif value.get("metadata"):
        request.metadata = {**(request.metadata or {}), **value["metadata"]}

    return await service.create_assistant(request, user.identity)


@router.get("/assistants", response_model=AssistantList, response_model_by_alias=False)
async def list_assistants(
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """List all assistants owned by the authenticated user.

    Returns every assistant without filtering. Use the search endpoint for
    filtered queries.
    """
    # Authorization check (search action for listing)
    ctx = build_auth_context(user, "assistants", "search")
    value = {}
    filters = await handle_event(ctx, value)

    # Apply filters if provided by handler
    if filters:
        # Convert filters to search request format
        search_request = AssistantSearchRequest(filters=filters)
        assistants = await service.search_assistants(search_request, user.identity)
    else:
        assistants = await service.list_assistants(user.identity)

    return AssistantList(assistants=assistants, total=len(assistants))


@router.post("/assistants/search", response_model=list[Assistant], response_model_by_alias=False)
async def search_assistants(
    request: AssistantSearchRequest,
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Search assistants with filters.

    Filter by name, description, graph ID, or metadata. Results are paginated
    via `limit` and `offset`.
    """
    # Authorization check
    ctx = build_auth_context(user, "assistants", "search")
    value = request.model_dump()
    filters = await handle_event(ctx, value)

    # Merge handler filters with request filters
    if filters:
        request_filters = request.filters or {}
        request.filters = {**request_filters, **filters}

    return await service.search_assistants(request, user.identity)


@router.post("/assistants/count", response_model=int)
async def count_assistants(
    request: AssistantSearchRequest,
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Count assistants matching the given filters.

    Accepts the same filter parameters as the search endpoint but returns only
    the total count.
    """
    # Authorization check (search action for counting)
    ctx = build_auth_context(user, "assistants", "search")
    value = request.model_dump()
    filters = await handle_event(ctx, value)

    # Merge handler filters with request filters
    if filters:
        request_filters = request.filters or {}
        request.filters = {**request_filters, **filters}

    return await service.count_assistants(request, user.identity)


@router.get(
    "/assistants/{assistant_id}",
    response_model=Assistant,
    response_model_by_alias=False,
    responses={**NOT_FOUND},
)
async def get_assistant(
    assistant_id: str,
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Get an assistant by its ID.

    Returns the latest version of the assistant. Returns 404 if the assistant
    does not exist or does not belong to the authenticated user.
    """
    # Authorization check
    ctx = build_auth_context(user, "assistants", "read")
    value = {"assistant_id": assistant_id}
    await handle_event(ctx, value)

    return await service.get_assistant(assistant_id, user.identity)


@router.patch(
    "/assistants/{assistant_id}",
    response_model=Assistant,
    response_model_by_alias=False,
    responses={**NOT_FOUND},
)
async def update_assistant(
    assistant_id: str,
    request: AssistantUpdate,
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Update an assistant by its ID.

    Partial update: only fields included in the request body are changed.
    Creates a new version of the assistant.
    """
    # Authorization check
    ctx = build_auth_context(user, "assistants", "update")
    value = {**request.model_dump(), "assistant_id": assistant_id}
    filters = await handle_event(ctx, value)

    # If handler modified metadata, update request
    if filters and "metadata" in filters:
        request.metadata = {**(request.metadata or {}), **filters["metadata"]}
    elif value.get("metadata"):
        request.metadata = {**(request.metadata or {}), **value["metadata"]}

    return await service.update_assistant(assistant_id, request, user.identity)


@router.delete("/assistants/{assistant_id}", responses={**NOT_FOUND})
async def delete_assistant(
    assistant_id: str,
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Delete an assistant by its ID.

    Permanently removes the assistant and all of its versions. This action
    cannot be undone.
    """
    # Authorization check
    ctx = build_auth_context(user, "assistants", "delete")
    value = {"assistant_id": assistant_id}
    await handle_event(ctx, value)

    return await service.delete_assistant(assistant_id, user.identity)


@router.post(
    "/assistants/{assistant_id}/latest",
    response_model=Assistant,
    response_model_by_alias=False,
    responses={**NOT_FOUND},
)
async def set_assistant_latest(
    assistant_id: str,
    version: int = Body(..., embed=True, description="The version number to set as latest"),
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Pin a specific version as the latest version of an assistant.

    After calling this endpoint, the assistant will use the specified version's
    configuration when executing runs.
    """
    return await service.set_assistant_latest(assistant_id, version, user.identity)


@router.post(
    "/assistants/{assistant_id}/versions",
    response_model=list[Assistant],
    response_model_by_alias=False,
    responses={**NOT_FOUND},
)
async def list_assistant_versions(
    assistant_id: str,
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """List all versions of an assistant.

    Returns versions ordered from newest to oldest. Each version captures the
    assistant's configuration at the time of creation or update.
    """
    return await service.list_assistant_versions(assistant_id, user.identity)


@router.get(
    "/assistants/{assistant_id}/schemas",
    response_model=AgentSchemas,
    responses={**NOT_FOUND},
)
async def get_assistant_schemas(
    assistant_id: str,
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Get the JSON schemas for an assistant's graph.

    Returns the input, output, state, and config schemas derived from the
    underlying graph's type annotations.
    """
    return await service.get_assistant_schemas(assistant_id, user)


@router.get("/assistants/{assistant_id}/graph", responses={**NOT_FOUND})
async def get_assistant_graph(
    assistant_id: str,
    xray: bool | int | None = Query(
        None, description="Expand subgraph nodes. Pass true or a depth integer to control nesting."
    ),
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Get the graph structure for visualization.

    Returns a JSON representation of the graph's nodes and edges suitable for
    rendering in graph visualizers. Use `xray` to expand subgraph nodes into
    their internal structure.
    """
    # Default to False if not provided
    xray_value = xray if xray is not None else False
    return await service.get_assistant_graph(assistant_id, xray_value, user)


@router.get("/assistants/{assistant_id}/subgraphs", responses={**NOT_FOUND})
async def get_assistant_subgraphs(
    assistant_id: str,
    recurse: bool = Query(False, description="Recursively include nested subgraphs."),
    namespace: str | None = Query(None, description="Filter to a specific subgraph namespace."),
    user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    """Get subgraphs of an assistant.

    Returns the subgraph definitions used by this assistant's graph. Set
    `recurse=true` to include deeply nested subgraphs, or filter to a single
    namespace.
    """
    return await service.get_assistant_subgraphs(assistant_id, namespace, recurse, user)
