"""E2E tests for POST /threads/search sort and filter behavior."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient

from aegra_api.settings import settings
from tests.e2e._utils import elog, get_e2e_client


async def _seed_three_threads(tag: str) -> list[str]:
    """Create three threads tagged with a unique marker, spaced in time.

    Returns thread ids in creation order (oldest first).
    """
    client = get_e2e_client()
    ids: list[str] = []
    for i in range(3):
        thread = await client.threads.create(metadata={"search_test_tag": tag, "seq": str(i)})
        ids.append(thread["thread_id"])
        # Force distinct created_at timestamps
        await asyncio.sleep(0.05)
    elog(f"Seeded threads for tag {tag}", ids)
    return ids


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_search_order_by_created_at_asc_e2e() -> None:
    """order_by='created_at ASC' returns threads in creation order."""
    tag = f"sort-asc-{uuid.uuid4().hex[:8]}"
    created = await _seed_three_threads(tag)

    async with AsyncClient(base_url=settings.app.SERVER_URL, timeout=30.0) as http_client:
        resp = await http_client.post(
            "/threads/search",
            json={"metadata": {"search_test_tag": tag}, "order_by": "created_at ASC", "limit": 100},
        )
    assert resp.status_code == 200, resp.text
    returned = [t["thread_id"] for t in resp.json()]
    elog("ASC result", returned)
    assert returned == created


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_search_order_by_created_at_desc_e2e() -> None:
    """order_by='created_at DESC' returns threads newest-first."""
    tag = f"sort-desc-{uuid.uuid4().hex[:8]}"
    created = await _seed_three_threads(tag)

    async with AsyncClient(base_url=settings.app.SERVER_URL, timeout=30.0) as http_client:
        resp = await http_client.post(
            "/threads/search",
            json={"metadata": {"search_test_tag": tag}, "order_by": "created_at DESC", "limit": 100},
        )
    assert resp.status_code == 200, resp.text
    returned = [t["thread_id"] for t in resp.json()]
    elog("DESC result", returned)
    assert returned == list(reversed(created))


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_search_malformed_order_by_falls_back_e2e() -> None:
    """Unknown/malformed order_by must not 500 — falls back to default ordering."""
    tag = f"sort-bad-{uuid.uuid4().hex[:8]}"
    created = await _seed_three_threads(tag)

    async with AsyncClient(base_url=settings.app.SERVER_URL, timeout=30.0) as http_client:
        for bad in ["nonexistent_col", "password; DROP TABLE", ""]:
            resp = await http_client.post(
                "/threads/search",
                json={"metadata": {"search_test_tag": tag}, "order_by": bad, "limit": 100},
            )
            assert resp.status_code == 200, f"order_by={bad!r} → {resp.status_code}: {resp.text}"
            returned = {t["thread_id"] for t in resp.json()}
            assert returned == set(created), f"order_by={bad!r} dropped rows: {returned}"
