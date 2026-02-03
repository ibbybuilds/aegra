"""Fix imports in aegra_api package - convert all to absolute imports."""

import re
from pathlib import Path


def fix_imports(directory: Path) -> int:
    """Replace all imports with absolute aegra_api imports.

    Converts:
    - src.agent_server.* -> aegra_api.* (import statements)
    - agent_server.* -> aegra_api.* (old package name)
    - Relative imports (from .., from .) -> aegra_api.*
    - "src.agent_server.*" -> "aegra_api.*" (patch paths in tests)
    - "agent_server.*" -> "aegra_api.*" (patch paths with old name)

    Returns the number of files modified.
    """
    modified_count = 0

    for py_file in directory.rglob("*.py"):
        # Skip __pycache__ and .venv directories
        path_str = str(py_file)
        if "__pycache__" in path_str or ".venv" in path_str or "site-packages" in path_str:
            continue

        content = py_file.read_text(encoding="utf-8")
        original = content

        # Fix old absolute imports (import statements)
        # Order matters - fix more specific patterns first
        content = re.sub(r"from src\.agent_server\.", "from aegra_api.", content)
        content = re.sub(r"from src\.agent_server import", "from aegra_api import", content)
        content = re.sub(r"import src\.agent_server\.", "import aegra_api.", content)

        # Fix old package name (agent_server without src prefix)
        content = re.sub(r"from agent_server\.", "from aegra_api.", content)
        content = re.sub(r"from agent_server import", "from aegra_api import", content)
        content = re.sub(r"import agent_server\.", "import aegra_api.", content)

        # Fix patch paths in tests (string literals)
        # Matches: "src.agent_server.xyz" or 'src.agent_server.xyz'
        content = re.sub(r'"src\.agent_server\.', '"aegra_api.', content)
        content = re.sub(r"'src\.agent_server\.", "'aegra_api.", content)

        # Fix old package name in patch paths
        content = re.sub(r'"agent_server\.', '"aegra_api.', content)
        content = re.sub(r"'agent_server\.", "'aegra_api.", content)

        # Fix sys.modules references
        content = re.sub(r'sys\.modules\["src\.agent_server\.', 'sys.modules["aegra_api.', content)
        content = re.sub(r"sys\.modules\['src\.agent_server\.", "sys.modules['aegra_api.", content)
        content = re.sub(r'sys\.modules\["agent_server\.', 'sys.modules["aegra_api.', content)
        content = re.sub(r"sys\.modules\['agent_server\.", "sys.modules['aegra_api.", content)

        # Now fix relative imports - need to determine the module path
        # Get the relative path from directory root
        rel_path = py_file.relative_to(directory)
        parts = list(rel_path.parts[:-1])  # Directory parts, excluding filename

        # Process each line for relative imports
        lines = content.split("\n")
        new_lines = []
        for line in lines:
            new_line = fix_relative_import(line, parts)
            new_lines.append(new_line)
        content = "\n".join(new_lines)

        if content != original:
            py_file.write_text(content, encoding="utf-8")
            print(f"Fixed: {py_file}")
            modified_count += 1

    return modified_count


def fix_relative_import(line: str, current_path: list[str]) -> str:
    """Fix a single line's relative import to absolute.

    Args:
        line: The line of code
        current_path: List of directory parts from aegra_api root
                      e.g., ['api'] for aegra_api/api/runs.py
    """
    # Match: from ..module import X or from ..module.sub import X
    match = re.match(r"^(\s*)(from\s+)(\.+)(\S*)\s+(import.*)$", line)
    if not match:
        return line

    indent = match.group(1)
    from_kw = match.group(2)
    dots = match.group(3)
    module_path = match.group(4)
    import_part = match.group(5)

    # Calculate how many levels to go up
    levels_up = len(dots)

    # Handle edge case: from . import X (same directory)
    if levels_up == 1 and not module_path:
        # from . import X -> from aegra_api.current.path import X
        if current_path:
            absolute_module = "aegra_api." + ".".join(current_path)
        else:
            absolute_module = "aegra_api"
    elif levels_up == 1:
        # from .module import X -> from aegra_api.current.path.module import X
        if current_path:
            absolute_module = "aegra_api." + ".".join(current_path) + "." + module_path
        else:
            absolute_module = "aegra_api." + module_path
    else:
        # from ..module import X
        # Go up (levels_up - 1) from current path, then append module
        remaining_path = current_path[: len(current_path) - levels_up + 1]
        if module_path:
            if remaining_path:
                absolute_module = "aegra_api." + ".".join(remaining_path) + "." + module_path
            else:
                absolute_module = "aegra_api." + module_path
        else:
            if remaining_path:
                absolute_module = "aegra_api." + ".".join(remaining_path)
            else:
                absolute_module = "aegra_api"

    return f"{indent}{from_kw}{absolute_module} {import_part}"


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = Path("libs/aegra-api/src/aegra_api")

    print(f"Fixing imports in: {target}")
    print("Converting all imports to absolute 'aegra_api.*' format\n")
    count = fix_imports(target)
    print(f"\nModified {count} files")
