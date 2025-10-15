import msgspec
from typing import Any, Union
from .hotel_schema import Envelope
from msgspec.structs import asdict

# Reusable decoder avoids re-allocating internal tables on hot paths
decoder_envelope = msgspec.json.Decoder(type=Envelope)

def decode_hotels(raw: Union[str, bytes, bytearray]) -> Envelope:
    """Decode raw JSON from hotels API into a typed Envelope."""
    return decoder_envelope.decode(raw)

def decode_to_dict(raw: Union[str, bytes, bytearray]) -> Any:
    """Fast decode into dict/list (fallback or for ad-hoc peeks)."""
    return msgspec.json.decode(raw)

def envelope_to_dict(env: Envelope) -> dict:
    """Convert typed structs back to builtin dict/list types (rarely needed)."""
    return asdict(env, builtin_types=True)

def peek_status_and_token(raw: Union[str, bytes, bytearray]) -> tuple[str | None, str | None]:
    """
    Lightweight peek for polling loops. Uses dict-mode decode (still very fast).
    Returns (status, token) or (None, None) on failure.
    """
    try:
        d = msgspec.json.decode(raw)
        return d.get("status"), d.get("token")
    except Exception:
        return None, None