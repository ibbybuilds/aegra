#!/usr/bin/env python3
"""
JWT utility for API authentication
"""
import os
import time
import jwt
from typing import Optional

def create_jwt_token(jwt_secret: Optional[str] = None) -> str:
    """
    Create a JWT token for API authentication
    
    Args:
        jwt_secret: JWT secret from environment variable
        
    Returns:
        Encoded JWT token string
    """
    if not jwt_secret:
        jwt_secret = os.getenv("JWT_SECRET")
        if not jwt_secret:
            raise ValueError("JWT_SECRET environment variable is required")
    
    jwt_iss = os.getenv("JWT_ISS", "")
    current_timestamp = int(time.time() * 1000)  # Convert to milliseconds
    
    payload = {
        'iss': jwt_iss,
        'iat': current_timestamp,
        'exp': current_timestamp + 30000,  # 30 seconds from creation
        'jti': 'jwt_nonce'
    }
    
    try:
        token = jwt.encode(payload, jwt_secret, algorithm='HS256')
        return token
    except Exception as e:
        raise ValueError(f"Failed to create JWT token: {e}")

def get_auth_headers() -> dict:
    """
    Get authentication headers for the results API
    
    Returns:
        Dictionary containing Authorization header with JWT token
    """
    token = create_jwt_token()
    return {
        'Authorization': token,
        'pricing-id': '1'
    }
