"""A2A (Agent-to-Agent) protocol adapter.

Exposes agents via A2A JSON-RPC at /a2a/{assistant_id} with agent card
discovery at /.well-known/agent-card.json.
Uses the `a2a-sdk` library.
"""

from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from aegra_api.adapters.a2a_service import A2AService, get_a2a_service
from aegra_api.core.auth_deps import get_current_user
from aegra_api.core.orm import get_session
from aegra_api.models.auth import User
from aegra_api.services.streaming_service import streaming_service

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _rpc_ok(result: Any, rpc_id: Any) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response.

    Args:
        result: The result payload to include.
        rpc_id: The id from the original request.

    Returns:
        JSON-RPC success response dict.
    """
    return {"jsonrpc": "2.0", "result": result, "id": rpc_id}


def _rpc_error(code: int, message: str, rpc_id: Any) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response.

    Args:
        code: The JSON-RPC error code.
        message: Human-readable error description.
        rpc_id: The id from the original request.

    Returns:
        JSON-RPC error response dict.
    """
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": rpc_id}


# ---------------------------------------------------------------------------
# Route handler factories (closures capture the service instance)
# ---------------------------------------------------------------------------


def _make_well_known_handler(service: A2AService):  # type: ignore[return]
    """Return a route handler for GET /.well-known/agent-card.json.

    Args:
        service: The A2AService instance to use for building cards.

    Returns:
        An async route handler function.
    """

    async def _well_known_agent_card(
        request: Request, assistant_id: str | None = None
    ) -> JSONResponse:
        """Return the agent card for the given assistant or the first registered agent.

        Args:
            request: The incoming FastAPI request (used to derive base URL).
            assistant_id: Optional query param to select a specific agent.

        Returns:
            JSONResponse with the agent card dict.

        Raises:
            HTTPException: 404 when no agents are registered or assistant_id is unknown.
        """
        registry: dict[str, Any] = (
            service._langgraph_service._graph_registry if service._langgraph_service else {}
        )

        if not registry:
            raise HTTPException(status_code=404, detail="No agents registered")

        if assistant_id is not None:
            if assistant_id not in registry:
                raise HTTPException(
                    status_code=404, detail=f"Unknown assistant_id: {assistant_id!r}"
                )
            target_id = assistant_id
        else:
            target_id = next(iter(registry))

        graph_meta: Any = registry[target_id]
        name: str = (
            graph_meta.get("name", target_id) if isinstance(graph_meta, dict) else target_id
        )
        description: str = (
            graph_meta.get("description", f"Agent: {target_id}")
            if isinstance(graph_meta, dict)
            else f"Agent: {target_id}"
        )

        base_url: str = str(request.base_url).rstrip("/")
        card: dict[str, Any] = service.build_agent_card(
            assistant_id=target_id,
            name=name,
            description=description,
            base_url=base_url,
        )
        return JSONResponse(content=card)

    return _well_known_agent_card


def _make_agent_cards_handler(service: A2AService):  # type: ignore[return]
    """Return a route handler for GET /a2a/agent-cards.

    Args:
        service: The A2AService instance to use for building cards.

    Returns:
        An async route handler function.
    """

    async def _list_agent_cards(request: Request) -> JSONResponse:
        """Return an array of agent cards for all registered agents.

        Args:
            request: The incoming FastAPI request (used to derive base URL).

        Returns:
            JSONResponse with a JSON array of agent card dicts.
        """
        registry: dict[str, Any] = (
            service._langgraph_service._graph_registry if service._langgraph_service else {}
        )

        base_url: str = str(request.base_url).rstrip("/")
        cards: list[dict[str, Any]] = []
        for agent_id, graph_meta in registry.items():
            name: str = (
                graph_meta.get("name", agent_id) if isinstance(graph_meta, dict) else agent_id
            )
            description: str = (
                graph_meta.get("description", f"Agent: {agent_id}")
                if isinstance(graph_meta, dict)
                else f"Agent: {agent_id}"
            )
            card: dict[str, Any] = service.build_agent_card(
                assistant_id=agent_id,
                name=name,
                description=description,
                base_url=base_url,
            )
            cards.append(card)
        return JSONResponse(content=cards)

    return _list_agent_cards


def _make_rpc_handler(service: A2AService):  # type: ignore[return]
    """Return a route handler for POST /a2a/{assistant_id}.

    Args:
        service: The A2AService instance to dispatch JSON-RPC calls to.

    Returns:
        An async route handler function.
    """

    async def _a2a_rpc(
        request: Request,
        assistant_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> Response:
        """Handle A2A JSON-RPC requests for a specific agent.

        Parses the JSON-RPC body and dispatches to the appropriate A2AService
        method based on the ``method`` field.

        Supported methods:
        - ``message/send``: Execute the agent and return the resulting Task.
        - ``tasks/get``: Look up an existing task by ID.
        - ``tasks/cancel``: Cancel a running task and return its updated state.
        - ``message/stream``: Not yet implemented; returns -32603 error.

        Args:
            request: The incoming FastAPI request.
            assistant_id: Path parameter identifying the target agent.

        Returns:
            JSONResponse containing a JSON-RPC 2.0 response envelope.
        """
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse(content=_rpc_error(-32700, "Parse error: invalid JSON", None))

        rpc_id: Any = body.get("id")
        method: str = body.get("method", "")
        params: dict[str, Any] = body.get("params") or {}

        if method == "message/send":
            message: dict[str, Any] = params.get("message") or {}
            parts: list[dict[str, Any]] = message.get("parts") or []
            context_id: str | None = params.get("contextId") or message.get("contextId")
            task_id: str | None = params.get("taskId") or message.get("taskId")
            try:
                result: dict[str, Any] = await service.send_message(
                    assistant_id=assistant_id,
                    parts=parts,
                    user=user,
                    context_id=context_id,
                    task_id=task_id,
                )
            except ValueError as exc:
                return JSONResponse(content=_rpc_error(-32602, str(exc), rpc_id))
            except Exception as exc:
                logger.error(
                    "A2A send_message error", error=str(exc), assistant_id=assistant_id
                )
                return JSONResponse(content=_rpc_error(-32603, f"Internal error: {exc}", rpc_id))
            return JSONResponse(content=_rpc_ok(result, rpc_id))

        if method == "tasks/get":
            task_id_param: str | None = (
                params.get("id") or params.get("taskId")
            ) if params else None
            if not task_id_param:
                return JSONResponse(
                    content=_rpc_error(-32602, "Missing required param: id", rpc_id)
                )
            try:
                task_result: dict[str, Any] = await service.get_task(task_id_param)
            except ValueError as exc:
                return JSONResponse(content=_rpc_error(-32602, str(exc), rpc_id))
            except Exception as exc:
                logger.error("A2A get_task error", error=str(exc), task_id=task_id_param)
                return JSONResponse(content=_rpc_error(-32603, f"Internal error: {exc}", rpc_id))
            return JSONResponse(content=_rpc_ok(task_result, rpc_id))

        if method == "tasks/cancel":
            cancel_task_id: str | None = (
                params.get("id") or params.get("taskId")
            ) if params else None
            if not cancel_task_id:
                return JSONResponse(
                    content=_rpc_error(-32602, "Missing required param: id", rpc_id)
                )
            try:
                await streaming_service.cancel_run(cancel_task_id)
                cancelled_task: dict[str, Any] = await service.get_task(cancel_task_id)
            except ValueError as exc:
                return JSONResponse(content=_rpc_error(-32602, str(exc), rpc_id))
            except Exception as exc:
                logger.error("A2A tasks/cancel error", error=str(exc), task_id=cancel_task_id)
                return JSONResponse(content=_rpc_error(-32603, f"Internal error: {exc}", rpc_id))
            return JSONResponse(content=_rpc_ok(cancelled_task, rpc_id))

        if method == "message/stream":
            message = params.get("message") or {}
            parts = message.get("parts") or []
            context_id = params.get("contextId") or message.get("contextId")
            task_id = params.get("taskId") or message.get("taskId")
            try:
                event_stream = service.stream_message(
                    assistant_id=assistant_id,
                    parts=parts,
                    user=user,
                    session=session,
                    context_id=context_id,
                    task_id=task_id,
                )
                return StreamingResponse(
                    event_stream,
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
            except ValueError as exc:
                return JSONResponse(content=_rpc_error(-32602, str(exc), rpc_id))
            except Exception as exc:
                logger.error(
                    "A2A message/stream error", error=str(exc), assistant_id=assistant_id
                )
                return JSONResponse(content=_rpc_error(-32603, f"Internal error: {exc}", rpc_id))

        return JSONResponse(
            content=_rpc_error(-32601, f"Method not found: {method!r}", rpc_id)
        )

    return _a2a_rpc


# ---------------------------------------------------------------------------
# Adapter mount
# ---------------------------------------------------------------------------


def mount_a2a(app: FastAPI) -> None:
    """Mount A2A endpoints on the FastAPI app.

    Registers:
    - GET /.well-known/agent-card.json - Agent card discovery
    - GET /a2a/agent-cards        - List all agent cards (Aegra extension)
    - POST /a2a/{assistant_id}    - JSON-RPC endpoint

    Route handlers are built as closures capturing the A2AService singleton so
    that tests can inject a custom service instance via a patch on
    ``get_a2a_service`` before calling this function.

    Args:
        app: The FastAPI application to mount on.
    """
    service: A2AService = get_a2a_service()

    app.add_api_route(
        "/.well-known/agent-card.json",
        _make_well_known_handler(service),
        methods=["GET"],
        include_in_schema=False,
    )
    # /a2a/agent-cards MUST be registered before /a2a/{assistant_id} so the
    # static path wins over the dynamic one.
    app.add_api_route(
        "/a2a/agent-cards",
        _make_agent_cards_handler(service),
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/a2a/{assistant_id}",
        _make_rpc_handler(service),
        methods=["POST"],
        include_in_schema=False,
        response_model=None,
    )
    logger.info(
        "A2A adapter mounted",
        routes=["/.well-known/agent-card.json", "/a2a/agent-cards", "/a2a/{assistant_id}"],
    )
