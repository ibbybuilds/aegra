"""Store endpoints for Agent Protocol"""

from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Query

from ..core.auth_deps import get_current_user
from ..models import (
    StoreDeleteRequest,
    StoreGetResponse,
    StoreItem,
    StorePutRequest,
    StoreSearchRequest,
    StoreSearchResponse,
    User,
)

router = APIRouter()


@router.put("/store/items")
async def put_store_item(
    request: StorePutRequest, user: User = Depends(get_current_user)
):
    """Store an item in the LangGraph store"""

    # Apply user namespace scoping
    scoped_namespace = apply_user_namespace_scoping(user.identity, request.namespace)

    # Get LangGraph store from database manager
    from ..core.database import db_manager

    store = await db_manager.get_store()

    await store.aput(
        namespace=tuple(scoped_namespace), key=request.key, value=request.value
    )

    return {"status": "stored"}


@router.get("/store/items", response_model=StoreGetResponse)
async def get_store_item(
    key: str,
    namespace: Union[str, list[str], None] = Query(None),
    user: User = Depends(get_current_user),
):
    """Get an item from the LangGraph store"""

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

    # Get LangGraph store from database manager
    from ..core.database import db_manager

    store = await db_manager.get_store()

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
):
    """Delete an item from the LangGraph store.

    Compatible with SDK which sends JSON body {namespace, key}.
    Also accepts query params for manual usage.
    """
    # Determine source of parameters
    if body is not None:
        ns = body.namespace
        k = body.key
    else:
        if key is None:
            raise HTTPException(422, "Missing 'key' parameter")
        ns = namespace or []
        k = key

    # Apply user namespace scoping
    scoped_namespace = apply_user_namespace_scoping(user.identity, ns)

    # Get LangGraph store from database manager
    from ..core.database import db_manager

    store = await db_manager.get_store()

    await store.adelete(tuple(scoped_namespace), k)

    return {"status": "deleted"}


@router.post("/store/items/search", response_model=StoreSearchResponse)
async def search_store_items(
    request: StoreSearchRequest, user: User = Depends(get_current_user)
):
    """Search items in the LangGraph store"""

    # Apply user namespace scoping
    scoped_prefix = apply_user_namespace_scoping(
        user.identity, request.namespace_prefix
    )

    # Get LangGraph store from database manager
    from ..core.database import db_manager

    store = await db_manager.get_store()

    # Search with LangGraph store
    # asearch takes namespace_prefix as a positional-only argument
    results = await store.asearch(
        tuple(scoped_prefix),
        query=request.query,
        limit=request.limit or 20,
        offset=request.offset or 0,
    )

    items = [
        StoreItem(key=r.key, value=r.value, namespace=list(r.namespace))
        for r in results
    ]

    return StoreSearchResponse(
        items=items,
        total=len(items),  # LangGraph store doesn't provide total count
        limit=request.limit or 20,
        offset=request.offset or 0,
    )


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
