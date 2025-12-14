"""
Example custom routes file for Aegra.

This demonstrates how to add custom FastAPI endpoints to your Aegra server.

Configuration:
Add this to your aegra.json or langgraph.json:

{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  },
  "http": {
    "app": "./custom_routes_example.py:app"
  }
}

You can also configure authentication and CORS:

{
  "http": {
    "app": "./custom_routes_example.py:app",
    "enable_custom_route_auth": false,
    "cors": {
      "allow_origins": ["https://example.com"],
      "allow_credentials": true
    }
  }
}
"""

from fastapi import FastAPI, HTTPException

# Create your FastAPI app instance
# This will be merged with Aegra's core routes
app = FastAPI(
    title="Custom Routes",
    description="Custom endpoints for Aegra",
)


@app.get("/custom/hello")
async def hello():
    """Simple custom endpoint"""
    return {"message": "Hello from custom route!", "status": "ok"}


@app.post("/custom/webhook")
async def webhook(data: dict):
    """Example webhook endpoint"""
    return {
        "received": data,
        "status": "processed",
        "message": "Webhook received successfully",
    }


@app.get("/custom/stats")
async def stats():
    """Example stats endpoint"""
    return {
        "total_requests": 1000,
        "active_sessions": 42,
        "uptime": "2 days",
    }


# You can override shadowable routes like the root endpoint
# Note: Core API routes (/assistants, /threads, /runs, /store) cannot be overridden
@app.get("/")
async def custom_root():
    """Custom root endpoint - overrides Aegra's default root"""
    return {
        "message": "Custom Aegra Server",
        "version": "0.1.0",
        "status": "running",
        "custom": True,
    }


# Example of accessing Aegra's database/services
@app.get("/custom/db-status")
async def db_status():
    """Check database status using Aegra's db_manager"""
    try:
        from src.agent_server.core.database import db_manager

        if db_manager.engine:
            return {"database": "connected", "status": "ok"}
        return {"database": "not_initialized", "status": "error"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Database check failed: {str(e)}"
        ) from e


# Example with authentication (if enable_custom_route_auth is True)
@app.get("/custom/protected")
async def protected_endpoint():
    """Protected endpoint - requires authentication if enable_custom_route_auth is True"""
    return {
        "message": "This endpoint is protected",
        "note": "Set enable_custom_route_auth: true in http config to enable auth",
    }
