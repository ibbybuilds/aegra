"""Test JSearch API for job listings."""

import asyncio
import httpx


async def test_jsearch():
    """Test JSearch API with the provided key."""
    api_key = "0b84d2ea43msh106eac4fea5cc47p1588e0jsnf253be95c723"
    
    queries = [
        "data analyst jobs remote",
        "data scientist jobs in Netherlands",
        "python developer entry level",
    ]
    
    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://jsearch.p.rapidapi.com/search",
                    headers={
                        "x-rapidapi-host": "jsearch.p.rapidapi.com",
                        "x-rapidapi-key": api_key,
                    },
                    params={
                        "query": query,
                        "page": 1,
                        "num_pages": 1,
                        "date_posted": "week",  # only recent jobs
                    },
                    timeout=15.0,
                )
                
                print(f"Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    jobs = data.get("data", [])
                    print(f"Jobs found: {len(jobs)}")
                    
                    for i, job in enumerate(jobs[:5]):
                        title = job.get("job_title", "No title")
                        company = job.get("employer_name", "Unknown")
                        location = job.get("job_city", "") or job.get("job_country", "")
                        url = job.get("job_apply_link", "")
                        is_remote = job.get("job_is_remote", False)
                        
                        print(f"\n  [{i+1}] {title}")
                        print(f"      Company: {company}")
                        print(f"      Location: {location} {'(Remote)' if is_remote else ''}")
                        print(f"      Apply: {url[:70]}..." if url else "      No apply link")
                else:
                    print(f"Error: {response.text}")
                    
        except Exception as e:
            print(f"Exception: {e}")


if __name__ == "__main__":
    asyncio.run(test_jsearch())
