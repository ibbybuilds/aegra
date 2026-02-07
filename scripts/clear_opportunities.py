"""Script to delete all opportunities from the database."""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.agent_server.core.accountability_orm import DiscoveredOpportunity
from src.agent_server.settings import settings


async def clear_all_opportunities():
    """Delete all opportunities from the database."""
    # Get database URL from settings (lowercase property)
    database_url = settings.db.database_url
    print(f"Connecting to database...")
    
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Count existing opportunities
        count_result = await session.execute(
            text("SELECT COUNT(*) FROM discovered_opportunities")
        )
        count = count_result.scalar()
        print(f"Found {count} opportunities to delete...")
        
        # Delete all opportunities
        await session.execute(delete(DiscoveredOpportunity))
        await session.commit()
        
        print(f"✅ Successfully deleted {count} opportunities!")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(clear_all_opportunities())
