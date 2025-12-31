import asyncio
import textwrap

import httpx
import structlog


async def warmup_cache():
    """
    Blocking Task Example Usage

    These tasks should be used to perform actions which need to be completed before deploying other langgraph services (e.g. sql cache warming, building lookup indices, fetching configurations, ...)
    """
    logger = structlog.get_logger(__name__)
    logger.info(
        "🕑 Simulating cache warming for a few seconds... Server won't start until this is done"
    )
    await asyncio.sleep(5)
    logger.info("✅ Cache warming simulation done !")


async def call_webhook():
    """
    Non-blocking Task Example Usage

    These tasks should be used to perform actions whose completion isn't required to provide proper services (e.g. setup additional features, webhook calls, periodic tasks, ...)
    """
    logger = structlog.get_logger(__name__)
    endpoint = "https://example.com/"
    logger.info(f"🌐 Requesting webpage at {endpoint}")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(endpoint)
        logger.info(
            f"➡️ Data received from {endpoint}...",
            data=textwrap.shorten(text=resp.text, width=50),
        )

    except httpx.RequestError as e:
        logger.error("❌ Request error in startup hook: " + str(e))


async def periodic_task():
    """
    Another Non-blocking Task Example : Periodic tasks
    """
    logger = structlog.get_logger(__name__)
    loops, max_loops = 0, 10

    while loops < max_loops:
        loops += 1
        logger.info(f"🔄️ Periodic Task Loop Count : {loops}/{max_loops}")
        await asyncio.sleep(3)
