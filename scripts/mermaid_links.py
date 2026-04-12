"""Generate mermaid.live fullscreen URLs for Mermaid diagrams in docs.

Scans .mdx files for ```mermaid blocks and prints shareable mermaid.live
URLs for each diagram. Uses only Python builtins (zlib + base64).

Usage:
    python scripts/mermaid_links.py                          # scan all docs
    python scripts/mermaid_links.py docs/guides/worker-architecture.mdx  # single file
"""

import base64
import json
import re
import sys
import zlib
from pathlib import Path


def mermaid_live_url(diagram: str, *, theme: str = "dark") -> str:
    """Encode a Mermaid diagram into a mermaid.live shareable URL."""
    state = json.dumps({"code": diagram, "mermaid": {"theme": theme}})
    compressed = zlib.compress(state.encode(), 9)
    encoded = base64.urlsafe_b64encode(compressed).decode()
    return f"https://mermaid.live/view#pako:{encoded}"


def extract_mermaid_blocks(text: str) -> list[str]:
    """Extract all ```mermaid code blocks from text."""
    return re.findall(r"```mermaid\n(.*?)\n```", text, re.DOTALL)


def process_file(path: Path) -> None:
    """Print mermaid.live URLs for all diagrams in a file."""
    content = path.read_text(encoding="utf-8")
    blocks = extract_mermaid_blocks(content)

    if not blocks:
        return

    print(f"\n{'=' * 60}")
    print(f"  {path}")
    print(f"{'=' * 60}")

    for i, block in enumerate(blocks, 1):
        first_line = block.strip().split("\n")[0]
        url = mermaid_live_url(block.strip())
        print(f"\n  Diagram {i}: {first_line[:50]}")
        print(f"  {url}")


def main() -> None:
    args = sys.argv[1:]

    if args:
        paths = [Path(a) for a in args]
    else:
        docs_dir = Path(__file__).parent.parent / "docs"
        paths = sorted(docs_dir.rglob("*.mdx"))

    total = 0
    for path in paths:
        if not path.exists():
            print(f"  File not found: {path}", file=sys.stderr)
            continue
        blocks = extract_mermaid_blocks(path.read_text(encoding="utf-8"))
        if blocks:
            total += len(blocks)
            process_file(path)

    print(f"\n  Found {total} diagram(s) across {len(paths)} file(s).")


if __name__ == "__main__":
    main()
