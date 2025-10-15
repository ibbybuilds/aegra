from __future__ import annotations
import base64
import json
from typing import Dict, Any

def make_cursor(key: str, pos: int, ver: str) -> str:
    """Encode a stable, stateless cursor over a frozen array."""
    blob = {"key": key, "pos": int(pos), "ver": ver}
    raw = json.dumps(blob, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")

def read_cursor(cursor: str) -> Dict[str, Any]:
    """Decode a cursor back to its components."""
    data = base64.urlsafe_b64decode(cursor.encode("utf-8"))
    return json.loads(data.decode("utf-8"))