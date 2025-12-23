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
        # Monitor ALL paths by default to catch errors from conversation-relay
        # You can add paths to excluded_paths if needed to reduce noise
        self.excluded_paths = [
            "/health",  # Skip health check
            "/docs",    # Skip OpenAPI docs
            "/redoc",   # Skip ReDoc
            "/openapi.json",  # Skip OpenAPI schema
        ]

    def should_monitor(self, path: str) -> bool:
        """Check if this path should be monitored for JSON errors."""
        # Monitor all paths except excluded ones
        return not any(excluded in path for excluded in self.excluded_paths)

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
                            # === COMPRESSION/TRUNCATION DETECTION ===
                            # Step 0: Check for Content-Length mismatch and compression
                            content_length_header = headers.get(b"content-length", b"")
                            content_encoding_header = headers.get(b"content-encoding", b"")

                            declared_length = (
                                int(content_length_header.decode("latin1"))
                                if content_length_header
                                else None
                            )
                            actual_length = len(raw_body)

                            # Check if body is gzip-compressed (starts with magic bytes 0x1f 0x8b)
                            is_gzipped = len(raw_body) >= 2 and raw_body[:2] == b"\x1f\x8b"

                            # Log comprehensive request diagnostics
                            logger.info(
                                f"[JSON_DEBUG] Received JSON request to {path}",
                                method=method,
                                path=path,
                                content_type=content_type,
                                content_encoding=content_encoding_header.decode("latin1") if content_encoding_header else None,
                                declared_content_length=declared_length,
                                actual_body_size_bytes=actual_length,
                                is_gzipped=is_gzipped,
                                first_2_bytes_hex=raw_body[:2].hex() if len(raw_body) >= 2 else None,
                            )

                            # Log first and last 200 bytes to identify truncation
                            logger.info(
                                "[JSON_DEBUG] Body preview",
                                first_200_bytes=raw_body[:200],
                                last_200_bytes=raw_body[-200:] if len(raw_body) > 200 else raw_body,
                            )

                            # Check for Content-Length mismatch (red flag for truncation!)
                            if declared_length is not None and declared_length != actual_length:
                                logger.error(
                                    "⚠️ [JSON_DEBUG] CONTENT-LENGTH MISMATCH DETECTED!",
                                    declared_content_length=declared_length,
                                    actual_body_size=actual_length,
                                    difference_bytes=declared_length - actual_length,
                                    is_gzipped=is_gzipped,
                                    content_encoding=content_encoding_header.decode("latin1") if content_encoding_header else None,
                                    diagnosis=(
                                        "Body appears gzip-compressed but Content-Length mismatch detected. "
                                        "Likely cause: reverse proxy compressed body without updating Content-Length header."
                                        if is_gzipped
                                        else "Content-Length header does not match actual body size. Possible truncation."
                                    ),
                                )

                            # Check if gzipped but no Content-Encoding header
                            if is_gzipped and not content_encoding_header:
                                logger.warning(
                                    "[JSON_DEBUG] Gzip-compressed body without Content-Encoding header",
                                    is_gzipped=is_gzipped,
                                    content_encoding_present=bool(content_encoding_header),
                                    diagnosis="Body is gzip-compressed (starts with 0x1f8b) but Content-Encoding header is missing. Transparent compression may be occurring.",
                                )

                            # If gzipped, attempt to decompress and log results
                            if is_gzipped:
                                try:
                                    import gzip

                                    decompressed_body = gzip.decompress(raw_body)
                                    logger.info(
                                        "[JSON_DEBUG] Successfully decompressed gzip body",
                                        compressed_size=len(raw_body),
                                        decompressed_size=len(decompressed_body),
                                        compression_ratio=f"{len(raw_body) / len(decompressed_body):.2%}",
                                    )
                                    # Replace raw_body with decompressed version for further processing
                                    raw_body = decompressed_body
                                except Exception as decompress_err:
                                    logger.error(
                                        "[JSON_DEBUG] Failed to decompress gzip body",
                                        error=str(decompress_err),
                                        error_type=type(decompress_err).__name__,
                                    )

                            # Log request metadata
                            logger.info(
                                f"[JSON_DEBUG] Processing body (after decompression if applicable)",
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
