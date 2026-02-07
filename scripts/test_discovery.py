"""Test script to debug opportunity discovery."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "libs", "aegra-api", "src"))

from aegra_api.services.opportunity_discovery import opportunity_engine
from aegra_api.settings import settings


async def test_brave_search():
    """Test Brave Search API with job queries."""
    print(f"Brave API Key configured: {bool(settings.discovery.BRAVE_API_KEY)}")
    print(f"Key prefix: {settings.discovery.BRAVE_API_KEY[:8] if settings.discovery.BRAVE_API_KEY else 'N/A'}...")
    
    # Test job queries
    location = "remote"
    track = "data-analytics"
    
    print(f"\n=== Testing Job Queries for {track} in {location} ===")
    job_queries = opportunity_engine.build_job_queries(track, location)
    print(f"Generated queries: {job_queries}")
    
    for query in job_queries[:2]:
        print(f"\n--- Query: {query} ---")
        results = await opportunity_engine.brave_search(query)
        print(f"Results count: {len(results)}")
        
        for i, result in enumerate(results):
            url = result.get("url", "")
            title = result.get("title", "")
            print(f"  [{i+1}] {title[:60]}...")
            print(f"      URL: {url}")
            
            # Try to parse
            parsed = opportunity_engine.parse_job_result(result, track, location)
            if parsed:
                print(f"      ✅ PARSED as job: {parsed['title'][:50]}")
            else:
                print(f"      ❌ FILTERED OUT (not recognized as job)")
    
    print(f"\n=== Testing Event Queries for {track} in {location} ===")
    event_queries = opportunity_engine.build_event_queries(track, location)
    print(f"Generated queries: {event_queries}")
    
    for query in event_queries[:1]:
        print(f"\n--- Query: {query} ---")
        results = await opportunity_engine.brave_search(query)
        print(f"Results count: {len(results)}")
        
        for i, result in enumerate(results[:3]):
            url = result.get("url", "")
            title = result.get("title", "")
            print(f"  [{i+1}] {title[:60]}...")


if __name__ == "__main__":
    asyncio.run(test_brave_search())
