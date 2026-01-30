#!/usr/bin/env python3
"""Generate JWT tokens for testing aegra authentication.

This script generates JWT tokens using the same configuration as aegra's
JWT authentication system. Useful for local development and testing.

Example usage:
    # Basic token with just user ID
    python scripts/generate_jwt_token.py --sub test-user

    # Token with full claims
    python scripts/generate_jwt_token.py \\
        --sub user-123 \\
        --name "John Doe" \\
        --email "john@example.com" \\
        --org "acme-corp" \\
        --scopes "read" "write" \\
        --exp 3600

    # Token with custom expiration (24 hours)
    python scripts/generate_jwt_token.py --sub test-user --exp 86400
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv


def generate_token(
    sub: str,
    name: str | None = None,
    email: str | None = None,
    org: str | None = None,
    scopes: list[str] | None = None,
    exp_seconds: int = 3600,
) -> str:
    """Generate a JWT token with the specified claims.

    Args:
        sub: Subject (user identifier) - REQUIRED
        name: User display name - OPTIONAL
        email: User email address - OPTIONAL
        org: Organization ID - OPTIONAL
        scopes: List of permission scopes - OPTIONAL
        exp_seconds: Expiration time in seconds from now (default: 1 hour)

    Returns:
        JWT token string (without "Bearer " prefix)

    Raises:
        ValueError: If required environment variables are missing
    """
    # Validate required environment variables
    jwt_secret = os.getenv("AEGRA_JWT_SECRET")
    # Support both AEGRA_JWT_ISSUERS (list) and AEGRA_JWT_ISSUER (single)
    issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER")
    jwt_issuer = issuers_str.split(",")[0].strip() if issuers_str else None
    jwt_audience = os.getenv("AEGRA_JWT_AUDIENCE")
    jwt_algorithm = os.getenv("AEGRA_JWT_ALGORITHM", "HS256")

    if not jwt_secret:
        raise ValueError(
            "AEGRA_JWT_SECRET environment variable is required. "
            "Set it in your .env file or export it."
        )
    if not jwt_issuer:
        raise ValueError(
            "AEGRA_JWT_ISSUERS (or AEGRA_JWT_ISSUER) environment variable is required. "
            "Set it in your .env file or export it."
        )
    if not jwt_audience:
        raise ValueError(
            "AEGRA_JWT_AUDIENCE environment variable is required. "
            "Set it in your .env file or export it."
        )

    # Build JWT payload
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,  # Required: subject (user ID)
        "iss": jwt_issuer,  # Required: issuer
        "aud": jwt_audience,  # Required: audience
        "iat": int(now.timestamp()),  # Issued at
        "exp": int((now + timedelta(seconds=exp_seconds)).timestamp()),  # Expiration
    }

    # Add optional claims
    if name:
        payload["name"] = name
    if email:
        payload["email"] = email
    if org:
        payload["org"] = org
    if scopes:
        payload["scopes"] = scopes

    # Encode token
    token = jwt.encode(payload, jwt_secret, algorithm=jwt_algorithm)

    return token


def main():
    """CLI entry point for JWT token generation."""
    # Load environment variables from .env file
    load_dotenv()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Generate JWT tokens for aegra authentication testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic token
  %(prog)s --sub test-user

  # Full token with all claims
  %(prog)s --sub user-123 --name "John Doe" --email "john@example.com" \\
           --org "acme-corp" --scopes "read" "write"

  # Token with 24-hour expiration
  %(prog)s --sub test-user --exp 86400

Environment variables required:
  AEGRA_JWT_SECRET    - Secret key for signing tokens
  AEGRA_JWT_ISSUER    - Token issuer (e.g., "conversation-relay")
  AEGRA_JWT_AUDIENCE  - Token audience (e.g., "aegra")
  AEGRA_JWT_ALGORITHM - Algorithm (default: HS256)
        """,
    )

    parser.add_argument(
        "--sub",
        required=True,
        help="Subject (user identifier) - REQUIRED",
    )
    parser.add_argument(
        "--name",
        help="User display name",
    )
    parser.add_argument(
        "--email",
        help="User email address",
    )
    parser.add_argument(
        "--org",
        help="Organization ID",
    )
    parser.add_argument(
        "--scopes",
        nargs="+",
        help="List of permission scopes (space-separated)",
    )
    parser.add_argument(
        "--exp",
        type=int,
        default=3600,
        help="Expiration time in seconds from now (default: 3600 = 1 hour)",
    )
    parser.add_argument(
        "--output-bearer",
        action="store_true",
        help="Output with 'Bearer ' prefix for direct use in curl/httpie",
    )

    args = parser.parse_args()

    try:
        # Generate token
        token = generate_token(
            sub=args.sub,
            name=args.name,
            email=args.email,
            org=args.org,
            scopes=args.scopes,
            exp_seconds=args.exp,
        )

        # Output token
        if args.output_bearer:
            print(f"Bearer {token}")
        else:
            print(token)

        # Print token info to stderr (so it doesn't interfere with piping)
        exp_time = datetime.now(timezone.utc) + timedelta(seconds=args.exp)
        print(f"\n✓ Token generated successfully", file=sys.stderr)
        print(f"  Subject: {args.sub}", file=sys.stderr)
        if args.name:
            print(f"  Name: {args.name}", file=sys.stderr)
        if args.email:
            print(f"  Email: {args.email}", file=sys.stderr)
        if args.org:
            print(f"  Organization: {args.org}", file=sys.stderr)
        if args.scopes:
            print(f"  Scopes: {', '.join(args.scopes)}", file=sys.stderr)
        print(
            f"  Expires: {exp_time.strftime('%Y-%m-%d %H:%M:%S UTC')} "
            f"({args.exp} seconds from now)",
            file=sys.stderr,
        )
        print(f"\nUsage:", file=sys.stderr)
        print(
            f'  curl -H "Authorization: Bearer <token>" http://localhost:8000/threads',
            file=sys.stderr,
        )

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
