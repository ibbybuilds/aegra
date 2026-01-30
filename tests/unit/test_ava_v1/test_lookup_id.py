"""Unit tests for lookup_id utility."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from graphs.ava_v1.shared_libraries.lookup_id import lookup_id


@pytest.mark.asyncio
async def test_lookup_id_uses_env_variable(monkeypatch):
    """Test that lookup_id uses PINECONE_SERVICE_URL environment variable."""
    custom_url = "https://custom-pinecone.example.com"
    monkeypatch.setenv("PINECONE_SERVICE_URL", custom_url)

    # Mock response with high confidence result
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "id": "hotel123",
                "name": "Test Hotel",
                "score": 0.95
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = await lookup_id("test hotel", "Miami")

        # Verify the custom URL was used
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == f"{custom_url}/search"

        # Verify result structure
        assert result["confidence"] == "high"
        assert result["hotels"][0]["id"] == "hotel123"


@pytest.mark.asyncio
async def test_lookup_id_uses_default_url_when_env_not_set(monkeypatch):
    """Test that lookup_id uses default URL when PINECONE_SERVICE_URL is not set."""
    # Unset the environment variable
    monkeypatch.delenv("PINECONE_SERVICE_URL", raising=False)

    # Mock response with high confidence result
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "id": "hotel456",
                "name": "Default Hotel",
                "score": 0.92
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = await lookup_id("default hotel", "Orlando")

        # Verify the default Railway URL was used
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://pinecone-service-local-staging-4870.up.railway.app/search"

        # Verify result structure
        assert result["confidence"] == "high"
        assert result["hotels"][0]["id"] == "hotel456"


@pytest.mark.asyncio
async def test_lookup_id_high_confidence_single_result():
    """Test that high confidence results return single match."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"id": "hotel1", "name": "Marriott Downtown", "score": 0.95},
            {"id": "hotel2", "name": "Marriott Uptown", "score": 0.85},
            {"id": "hotel3", "name": "Marriott Midtown", "score": 0.75}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = await lookup_id("Marriott", "Miami")

        assert result["confidence"] == "high"
        assert len(result["hotels"]) == 1
        assert result["hotels"][0]["id"] == "hotel1"
        assert "high-confidence match" in result["message"]


@pytest.mark.asyncio
async def test_lookup_id_low_confidence_multiple_results():
    """Test that low confidence results return all matches."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"id": "hotel1", "name": "Hotel A", "score": 0.85},
            {"id": "hotel2", "name": "Hotel B", "score": 0.80},
            {"id": "hotel3", "name": "Hotel C", "score": 0.75}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = await lookup_id("Hotel", "Tampa")

        assert result["confidence"] == "low"
        assert len(result["hotels"]) == 3
        assert result["top_score"] == 0.85
        assert "Found 3 hotels" in result["message"]


@pytest.mark.asyncio
async def test_lookup_id_no_results():
    """Test handling of empty results from API."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": []}

    with patch("httpx.AsyncClient") as mock_client:
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_context

        result = await lookup_id("nonexistent hotel", "Miami")

        assert "error" in result
        assert result["error"] == "no_results"
        assert "No hotels found" in result["message"]


@pytest.mark.asyncio
async def test_lookup_id_api_error():
    """Test handling of API errors."""
    mock_response = MagicMock()
    mock_response.status_code = 500

    def raise_error():
        raise httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

    mock_response.raise_for_status = raise_error

    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = await lookup_id("test hotel", "Miami")

        assert "error" in result
        assert result["error"] == "api_error"
        assert "500" in result["message"]


@pytest.mark.asyncio
async def test_lookup_id_timeout():
    """Test handling of timeout errors."""
    mock_post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = await lookup_id("test hotel", "Miami")

        assert "error" in result
        assert result["error"] == "timeout"
        assert "timed out" in result["message"]


@pytest.mark.asyncio
async def test_lookup_id_request_body_format():
    """Test that request body is correctly formatted."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [{"id": "hotel1", "name": "Test", "score": 0.95}]
    }
    mock_response.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        await lookup_id("Marriott", "Miami")

        # Verify request body format
        call_args = mock_post.call_args
        request_body = call_args[1]["json"]

        assert request_body["query"] == "Marriott Miami"
        assert request_body["limit"] == 3
        assert request_body["indexName"] == "hotels"
        assert call_args[1]["timeout"] == 10.0
