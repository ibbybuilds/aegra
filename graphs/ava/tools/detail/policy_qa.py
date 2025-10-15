import httpx
import json
import os
from typing import Annotated, Union, Dict, List, Any
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage

@tool(description="Answer a question about company policies.")
async def policy_qa(policy_question: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> Union[Command, str]:
    """
    Answer a question about company policies.

    Args:
        policy_question: Question about company policies
        tool_call_id: Tool call ID for tracking

    Returns:
        Command with ToolMessage containing policy answer
    """
    try:
        # Validate inputs
        if not policy_question or not policy_question.strip():
            raise ValueError("Policy question is required. Please provide the policy question from the user.")
        
        # Get base URL from environment variable
        railway_baseurl = os.getenv("RAILWAY_BASEURL")
        
        if not railway_baseurl:
            raise ValueError("RAILWAY_BASEURL environment variable is required")
        
        # Make API request
        auth_headers = {
            "Accept-Encoding": "br, gzip",
        }

        request_body = {
            "query": policy_question,
            "limit": 3,
            "indexName": "semantic-search"
        }
        
        async with httpx.AsyncClient(http2=True) as client:
            results_resp = await client.post(f"{railway_baseurl}/search", headers=auth_headers, json=request_body)
            results_resp.raise_for_status()
            
            # Get the response data
            results_data = results_resp.json()
            results_content = results_resp.content
        
        # Return the response
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(results_data, indent=2),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
        
    except Exception as e:
            # Handle any errors gracefully
        error_response = {
            "error": f"Failed to answer policy question: {str(e)}",
            "answer": None
        }
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(error_response, indent=2),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )