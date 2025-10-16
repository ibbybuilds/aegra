import os
from langchain_core.tools import tool
from tavily import TavilyClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))


# Search tool to use to do research
@tool(description="Search the internet for a given query.")
def internet_search(
    query: str,
    max_results: int = 3,
    include_raw_content: bool = False,
    tool_call_id: str = None,
):
    """Run a web search"""
    # Direct synchronous call to Tavily
    search_docs = tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        tool_call_id=tool_call_id,
    )
    return search_docs