"""Store endpoints for Agent Protocol"""

from fastapi import APIRouter, Depends, HTTPException, Query

from aegra_api.core.auth_deps import auth_dependency, get_current_user
from aegra_api.core.auth_handlers import build_auth_context, handle_event
from aegra_api.core.database import db_manager
from aegra_api.models import (
    StoreDeleteRequest,
    StoreGetResponse,
    StoreItem,
    StoreListNamespacesRequest,
    StoreListNamespacesResponse,
    StorePutRequest,
    StoreSearchRequest,
    StoreSearchResponse,
    User,
)

router = APIRouter(tags=["Store"], dependencies=auth_dependency)


@router.put("/store/items")
async def put_store_item(request: StorePutRequest, user: User = Depends(get_current_user)) -> dict[str, str]:
    """Store an item in the LangGraph store"""
    # Authorization check
    ctx = build_auth_context(user, "store", "put")
    value = request.model_dump()
    filters = await handle_event(ctx, value)

    # If handler modified namespace/key/value, update request
    if filters:
        if "namespace" in filters:
            request.namespace = filters["namespace"]
        if "key" in filters:
            request.key = filters["key"]
        if "value" in filters:
            request.value = filters["value"]

    # Apply user namespace scoping
    scoped_namespace = apply_user_namespace_scoping(user.identity, request.namespace)

    store = db_manager.get_store()

    await store.aput(namespace=tuple(scoped_namespace), key=request.key, value=request.value)

    return {"status": "stored"}


@router.get("/store/items", response_model=StoreGetResponse)
async def get_store_item(
    key: str,
    namespace: str | list[str] | None = Query(None),
    user: User = Depends(get_current_user),
) -> StoreGetResponse:
    """Get an item from the LangGraph store"""
    # Authorization check
    ctx = build_auth_context(user, "store", "get")
    value = {"key": key, "namespace": namespace}
    filters = await handle_event(ctx, value)

    # If handler modified namespace/key, update
    if filters:
        if "namespace" in filters:
            namespace = filters["namespace"]
        if "key" in filters:
            key = filters["key"]

    # Accept SDK-style dotted namespaces or list
    ns_list: list[str]
    if isinstance(namespace, str):
        ns_list = [part for part in namespace.split(".") if part]
    elif isinstance(namespace, list):
        ns_list = namespace
    else:
        ns_list = []

    # Apply user namespace scoping
    scoped_namespace = apply_user_namespace_scoping(user.identity, ns_list)

    store = db_manager.get_store()

    item = await store.aget(tuple(scoped_namespace), key)

    if not item:
        raise HTTPException(404, "Item not found")

    return StoreGetResponse(key=key, value=item.value, namespace=list(scoped_namespace))


@router.delete("/store/items")
async def delete_store_item(
    body: StoreDeleteRequest | None = None,
    key: str | None = Query(None),
    namespace: list[str] | None = Query(None),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Delete an item from the LangGraph store.

    Compatible with SDK which sends JSON body {namespace, key}.
    Also accepts query params for manual usage.
    """
    # Determine source of parameters
    ns = None
    k = None
    if body is not None:
        ns = body.namespace
        k = body.key
    else:
        if key is None:
            raise HTTPException(422, "Missing 'key' parameter")
        ns = namespace or []
        k = key

    # Authorization check
    ctx = build_auth_context(user, "store", "delete")
    value = {"namespace": ns, "key": k}
    filters = await handle_event(ctx, value)

    # If handler modified namespace/key, update
    if filters:
        if "namespace" in filters:
            ns = filters["namespace"]
        if "key" in filters:
            k = filters["key"]

    # Apply user namespace scoping
    scoped_namespace = apply_user_namespace_scoping(user.identity, ns)

    store = db_manager.get_store()

    await store.adelete(tuple(scoped_namespace), k)

    return {"status": "deleted"}


@router.post("/store/items/search", response_model=StoreSearchResponse)
async def search_store_items(
    request: StoreSearchRequest, user: User = Depends(get_current_user)
) -> StoreSearchResponse:
    """Search items in the LangGraph store"""
    # Authorization check
    ctx = build_auth_context(user, "store", "search")
    value = request.model_dump()
    filters = await handle_event(ctx, value)

    # Merge handler filters with request filters
    if filters:
        if "namespace_prefix" in filters:
            request.namespace_prefix = filters["namespace_prefix"]

        handler_filters = {k: v for k, v in filters.items() if k != "namespace_prefix"}
        if handler_filters:
            request.filter = {**(request.filter or {}), **handler_filters}

    # Apply user namespace scoping
    scoped_prefix = apply_user_namespace_scoping(user.identity, request.namespace_prefix)

    store = db_manager.get_store()

    # Search with LangGraph store
    # asearch takes namespace_prefix as a positional-only argument
    results = await store.asearch(
        tuple(scoped_prefix),
        query=request.query,
        filter=request.filter,
        limit=request.limit or 20,
        offset=request.offset or 0,
    )

    items = [StoreItem(key=r.key, value=r.value, namespace=list(r.namespace)) for r in results]

    return StoreSearchResponse(
        items=items,
        total=len(items),  # LangGraph store doesn't provide total count
        limit=request.limit or 20,
        offset=request.offset or 0,
    )


@router.post("/store/namespaces", response_model=StoreListNamespacesResponse)
async def list_namespaces(
    request: StoreListNamespacesRequest,
    user: User = Depends(get_current_user),
) -> StoreListNamespacesResponse:
    """List namespaces in the LangGraph store"""
    # Authorization check
    ctx = build_auth_context(user, "store", "search")
    value = request.model_dump()
    filters = await handle_event(ctx, value)

    # Apply authorization filters if handler provided any
    if filters:
        if "prefix" in filters:
            request.prefix = filters["prefix"]
        if "suffix" in filters:
            request.suffix = filters["suffix"]

    # Apply user namespace scoping to prefix
    scoped_prefix = apply_user_namespace_scoping(user.identity, request.prefix or [])
    prefix: tuple[str, ...] = tuple(scoped_prefix)
    suffix: tuple[str, ...] | None = tuple(request.suffix) if request.suffix else None

    store = db_manager.get_store()

    result = await store.alist_namespaces(
        prefix=prefix,
        suffix=suffix,
        max_depth=request.max_depth,
        limit=request.limit,
        offset=request.offset,
    )

    return StoreListNamespacesResponse(namespaces=[list(ns) for ns in result])


def apply_user_namespace_scoping(user_id: str, namespace: list[str]) -> list[str]:
    """Apply user-based namespace scoping for data isolation"""

    if not namespace:
        # Default to user's private namespace
        return ["users", user_id]

    # Allow explicit user namespaces
    if namespace[0] == "users" and len(namespace) >= 2 and namespace[1] == user_id:
        return namespace

    # For development, allow all namespaces (remove this for production)
    return namespace
