"""Entry point for running the aegra-api server: ``python -m aegra_api``

Sets the Windows-compatible event-loop policy **before** uvicorn creates its
event loop, which fixes the psycopg "ProactorEventLoop" error on Windows.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402

from aegra_api.settings import settings  # noqa: E402


def main() -> None:
    uvicorn.run(
        "aegra_api.main:app",
        host=settings.app.HOST,
        port=settings.app.PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
