"""Middleware for comprehensive JSON parsing error logging.

This middleware intercepts JSON requests and provides detailed logging
when parsing errors occur, including:
- Raw request body and headers
- UTF-8 decode errors
- JSON parse errors with context
- Non-ASCII character detection
- Round-trip validation
"""

import json
from collections.abc import MutableMapping
from typing import Any

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.getLogger(__name__)


def find_non_ascii_chars(text: str) -> list[dict[str, Any]]:
    """Find all non-ASCII characters in text with their positions and codes."""
    non_ascii = []
    for i, char in enumerate(text):
        if ord(char) > 127:  # Non-ASCII
            non_ascii.append(
                {
                    "position": i,
                    "character": char,
                    "ord": ord(char),
                    "hex": hex(ord(char)),
                    "context_before": text[max(0, i - 10) : i],
                    "context_after": text[i + 1 : min(len(text), i + 11)],
                }
            )
    return non_ascii


def get_context_around_position(
    text: str, position: int, context_size: int = 100
) -> tuple[str, str, str]:
    """Get context before, at, and after a specific position."""
    before = text[max(0, position - context_size) : position]
    at_pos = text[position] if position < len(text) else ""
    after = text[position + 1 : min(len(text), position + context_size + 1)]
    return before, at_pos, after


def scan_dict_for_non_ascii(data: Any, path: str = "") -> list[dict[str, Any]]:
    """Recursively scan dictionary for non-ASCII characters."""
    results = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            results.extend(scan_dict_for_non_ascii(value, current_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]"
            results.extend(scan_dict_for_non_ascii(item, current_path))
    elif isinstance(data, str):
        non_ascii = find_non_ascii_chars(data)
        if non_ascii:
            results.append(
                {
                    "path": path,
                    "value": data[:100] + "..." if len(data) > 100 else data,
                    "non_ascii_chars": non_ascii,
                }
            )

    return results


class JSONDebugMiddleware:
    """Middleware to log comprehensive JSON parsing error information.

    This middleware is specifically designed to debug 422 JSON decode errors
    by capturing and logging detailed information about request bodies that
    fail to parse as JSON.
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        # Only log for these paths (to avoid noise)
        self.monitored_paths = [
            "/threads/",  # All thread endpoints
        ]

    def should_monitor(self, path: str) -> bool:
        """Check if this path should be monitored for JSON errors."""
        return any(monitored in path for monitored in self.monitored_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").decode("latin1")

        # Only monitor POST/PUT/PATCH with JSON content on specific paths
        if (
            method in ["POST", "PUT", "PATCH"]
            and "json" in content_type.lower()
            and self.should_monitor(path)
        ):
            body_parts = []
            has_logged_error = False

            async def receive_wrapper() -> MutableMapping[str, Any]:
                nonlocal has_logged_error
                message = await receive()

                if message["type"] == "http.request":
                    body_parts.append(message.get("body", b""))

                    # Process when we have the complete body
                    if not message.get("more_body", False):
                        raw_body = b"".join(body_parts)

                        if raw_body:
                            # Log request metadata
                            logger.info(
                                f"[JSON_DEBUG] Received JSON request to {path}",
                                method=method,
                                path=path,
                                content_type=content_type,
                                body_length_bytes=len(raw_body),
                            )

                            # Step 1: Try to decode as UTF-8
                            try:
                                decoded_body = raw_body.decode("utf-8")
                            except UnicodeDecodeError as e:
                                logger.error(
                                    f"[JSON_DEBUG] UTF-8 decode error at position {e.start}",
                                    path=path,
                                    error_reason=e.reason,
                                    error_start=e.start,
                                    error_end=e.end,
                                    problematic_bytes=raw_body[
                                        max(0, e.start - 20) : e.end + 20
                                    ].hex(),
                                    content_type=content_type,
                                )
                                has_logged_error = True
                                # Let FastAPI handle the error
                                return message

                            # Step 2: Check for non-ASCII in raw body
                            non_ascii_in_raw = find_non_ascii_chars(decoded_body)
                            if non_ascii_in_raw:
                                logger.warning(
                                    f"[JSON_DEBUG] Found {len(non_ascii_in_raw)} non-ASCII characters in raw body",
                                    path=path,
                                    count=len(non_ascii_in_raw),
                                    first_few=non_ascii_in_raw[:5],  # Log first 5
                                )

                            # Step 3: Try to parse as JSON
                            try:
                                parsed_data = json.loads(decoded_body)

                                # Success! Log that parsing succeeded
                                logger.info(
                                    "[JSON_DEBUG] JSON parsing succeeded",
                                    path=path,
                                    json_size_chars=len(decoded_body),
                                    non_ascii_count=len(non_ascii_in_raw),
                                )

                                # Step 4: Scan parsed data for non-ASCII
                                non_ascii_in_parsed = scan_dict_for_non_ascii(
                                    parsed_data
                                )
                                if non_ascii_in_parsed:
                                    logger.info(
                                        "[JSON_DEBUG] Found non-ASCII in parsed data",
                                        path=path,
                                        locations=non_ascii_in_parsed,
                                    )

                                # Step 5: Optional round-trip validation
                                try:
                                    reserialized = json.dumps(
                                        parsed_data, ensure_ascii=False
                                    )
                                    if reserialized != decoded_body:
                                        logger.warning(
                                            "[JSON_DEBUG] Round-trip JSON differs from original",
                                            path=path,
                                            original_length=len(decoded_body),
                                            reserialized_length=len(reserialized),
                                        )
                                except Exception as round_trip_err:
                                    logger.warning(
                                        "[JSON_DEBUG] Round-trip serialization failed",
                                        path=path,
                                        error=str(round_trip_err),
                                    )

                            except json.JSONDecodeError as e:
                                # This is what we're looking for! Log comprehensive error details
                                before_context, at_char, after_context = (
                                    get_context_around_position(
                                        decoded_body, e.pos, context_size=300
                                    )
                                )

                                logger.error(
                                    f"[JSON_DEBUG] JSON parse error at position {e.pos}: {e.msg}",
                                    path=path,
                                    error_position=e.pos,
                                    error_line=e.lineno,
                                    error_column=e.colno,
                                    error_message=e.msg,
                                    content_type=content_type,
                                    body_length_bytes=len(raw_body),
                                    body_length_chars=len(decoded_body),
                                )

                                # Log character details at error position
                                if e.pos < len(decoded_body):
                                    logger.error(
                                        "[JSON_DEBUG] Character at error position",
                                        character=at_char,
                                        ord=ord(at_char),
                                        hex=hex(ord(at_char)),
                                    )

                                # Log context around error
                                logger.error(
                                    "[JSON_DEBUG] Context around error position (±300 chars)",
                                    before_300_chars=before_context,
                                    after_300_chars=after_context,
                                )

                                # Log a visual representation with marker
                                context_with_marker = (
                                    before_context
                                    + "[ERROR HERE]"
                                    + at_char
                                    + after_context
                                )
                                logger.error(
                                    f"[JSON_DEBUG] Visual context:\n{context_with_marker}",
                                )

                                # Log preceding and following 50 characters for immediate context
                                preceding_50 = decoded_body[max(0, e.pos - 50) : e.pos]
                                following_50 = decoded_body[
                                    e.pos + 1 : min(len(decoded_body), e.pos + 51)
                                ]
                                logger.error(
                                    "[JSON_DEBUG] Immediate context (±50 chars)",
                                    preceding_50_chars=preceding_50,
                                    following_50_chars=following_50,
                                )

                                # Log first 4000 characters of body (increased from 2000)
                                logger.error(
                                    "[JSON_DEBUG] First 4000 chars of body",
                                    body_preview=decoded_body[:4000],
                                )

                                # Also log the section around the error (±500 chars) for easier analysis
                                error_section_start = max(0, e.pos - 500)
                                error_section_end = min(len(decoded_body), e.pos + 500)
                                error_section = decoded_body[
                                    error_section_start:error_section_end
                                ]
                                logger.error(
                                    "[JSON_DEBUG] Section around error (±500 chars)",
                                    error_section=error_section,
                                    section_start_pos=error_section_start,
                                    section_end_pos=error_section_end,
                                )

                                has_logged_error = True
                                # Let FastAPI handle the error (will return 422)

                return message

            await self.app(scope, receive_wrapper, send)
        else:
            # Not a monitored JSON request, pass through
            await self.app(scope, receive, send)
