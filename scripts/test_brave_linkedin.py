"""Test Brave Search with LinkedIn job queries."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "libs", "aegra-api", "src"))

import httpx
from aegra_api.settings import settings


async def test_linkedin_job_search():
    """Test Brave Search API with LinkedIn job queries."""
    api_key = settings.discovery.BRAVE_API_KEY
    print(f"Brave API Key: {api_key[:10]}..." if api_key else "NOT SET")
    
    # Test queries - exactly as user specified
    queries = [
        "site:linkedin.com/jobs software engineer Amsterdam",
        "site:linkedin.com/jobs data analyst remote",
        "site:linkedin.com/jobs python developer",
        "site:indeed.com data scientist junior",
        "data analyst job Amsterdam hiring 2026",  # broader search
    ]
    
    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                    },
                    params={
                        "q": query,
                        "count": 10,
                        "freshness": "pm",  # past month
                    },
                    timeout=15.0,
                )
                
                print(f"Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("web", {}).get("results", [])
                    print(f"Results count: {len(results)}")
                    
                    for i, result in enumerate(results[:5]):
                        title = result.get("title", "No title")[:70]
                        url = result.get("url", "")
                        print(f"\n  [{i+1}] {title}")
                        print(f"      URL: {url[:80]}...")
                else:
                    print(f"Error: {response.text}")
                    
        except Exception as e:
            print(f"Exception: {e}")


if __name__ == "__main__":
    asyncio.run(test_linkedin_job_search())
