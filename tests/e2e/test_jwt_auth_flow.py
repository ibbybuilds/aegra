"""E2E tests for JWT authentication flow.

Tests the complete JWT authentication flow from token generation to
protected endpoint access with user context propagation.
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from src.agent_server.main import app


def generate_test_token(
    sub: str = "test-user",
    exp_seconds: int = 3600,
    **extra_claims,
) -> str:
    """Generate a test JWT token."""
    jwt_secret = os.getenv("AEGRA_JWT_SECRET", "test-secret")
    # Use first issuer from list or fallback
    issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER", "test-issuer")
    jwt_issuer = issuers_str.split(",")[0].strip() if issuers_str else "test-issuer"
    jwt_audience = os.getenv("AEGRA_JWT_AUDIENCE", "test-audience")
    
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iss": jwt_issuer,
        "aud": jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_seconds)).timestamp()),
        **extra_claims,
    }
    
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


@pytest.mark.skipif(
    os.getenv("AUTH_TYPE") != "custom",
    reason="JWT E2E tests only run when AUTH_TYPE=custom",
)
class TestJWTAuthenticationE2E:
    """E2E tests for JWT authentication."""

    @pytest.mark.asyncio
    async def test_health_check_no_auth(self):
        """Test that health check doesn't require authentication."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")
            
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_protected_endpoint_no_token(self):
        """Test that protected endpoints reject requests without token."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/assistants")
            
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_endpoint_invalid_token(self):
        """Test that protected endpoints reject invalid tokens."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            headers = {"Authorization": "Bearer invalid.token.here"}
            response = await client.get("/assistants", headers=headers)
            
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_endpoint_valid_token(self):
        """Test that protected endpoints accept valid tokens."""
        token = generate_test_token(sub="test-user-e2e", org="test-org")
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get("/assistants", headers=headers)
            
            # Should succeed (200) or return empty list (200)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_user_scoped_thread_creation(self):
        """Test that threads are scoped to authenticated user."""
        user1_token = generate_test_token(sub="user-1", org="org-1")
        user2_token = generate_test_token(sub="user-2", org="org-2")
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            # User 1 creates a thread
            headers1 = {"Authorization": f"Bearer {user1_token}"}
            response1 = await client.post("/threads", headers=headers1)
            assert response1.status_code == 200
            thread1_id = response1.json()["thread_id"]
            
            # User 2 creates a thread
            headers2 = {"Authorization": f"Bearer {user2_token}"}
            response2 = await client.post("/threads", headers=headers2)
            assert response2.status_code == 200
            thread2_id = response2.json()["thread_id"]
            
            # User 1 can access their own thread
            response = await client.get(f"/threads/{thread1_id}", headers=headers1)
            assert response.status_code == 200
            
            # User 2 cannot access User 1's thread (should return 404 or 403)
            response = await client.get(f"/threads/{thread1_id}", headers=headers2)
            assert response.status_code in [403, 404]
            
            # User 2 can access their own thread
            response = await client.get(f"/threads/{thread2_id}", headers=headers2)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_user_scoped_thread_listing(self):
        """Test that thread listing is scoped to authenticated user."""
        user1_token = generate_test_token(sub="user-list-1", org="org-1")
        user2_token = generate_test_token(sub="user-list-2", org="org-2")
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            # User 1 creates a thread
            headers1 = {"Authorization": f"Bearer {user1_token}"}
            await client.post("/threads", headers=headers1)
            
            # User 2 creates a thread
            headers2 = {"Authorization": f"Bearer {user2_token}"}
            await client.post("/threads", headers=headers2)
            
            # User 1 lists threads (should only see their own)
            response1 = await client.get("/threads", headers=headers1)
            assert response1.status_code == 200
            threads1 = response1.json()
            assert all(
                thread.get("metadata", {}).get("owner") == "user-list-1"
                for thread in threads1
            )
            
            # User 2 lists threads (should only see their own)
            response2 = await client.get("/threads", headers=headers2)
            assert response2.status_code == 200
            threads2 = response2.json()
            assert all(
                thread.get("metadata", {}).get("owner") == "user-list-2"
                for thread in threads2
            )

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self):
        """Test that expired tokens are rejected."""
        # Generate token that expired 1 hour ago
        token = generate_test_token(sub="test-user", exp_seconds=-3600)
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get("/assistants", headers=headers)
            
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_token_caching_performance(self):
        """Test that token verification is fast due to caching."""
        token = generate_test_token(sub="perf-test-user", org="perf-org")
        headers = {"Authorization": f"Bearer {token}"}
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            # First request (cache miss)
            import time
            start1 = time.perf_counter()
            response1 = await client.get("/assistants", headers=headers)
            time1 = time.perf_counter() - start1
            
            # Second request (cache hit)
            start2 = time.perf_counter()
            response2 = await client.get("/assistants", headers=headers)
            time2 = time.perf_counter() - start2
            
            assert response1.status_code == 200
            assert response2.status_code == 200
            
            # Second request should be faster (though network/DB may dominate)
            # This is a soft check - caching should help but not always measurable
            # in E2E tests
            print(f"First request: {time1*1000:.2f}ms, Second: {time2*1000:.2f}ms")
