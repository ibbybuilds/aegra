"""Environment file loading utilities."""

import os
from pathlib import Path

from dotenv import dotenv_values


def load_env_file(env_file: Path | None) -> Path | None:
    """Load environment variables from a .env file using python-dotenv.

    Existing environment variables take precedence and are not overwritten.

    Args:
        env_file: Path to .env file, or None to use default (.env in cwd)

    Returns:
        Path to the loaded .env file, or None if not found
    """
    # Determine which file to load
    if env_file is not None:
        target = env_file
    else:
        # Default: look for .env in current directory
        target = Path.cwd() / ".env"

    if not target.is_file():
        return

    # Parse .env file and set vars (existing env vars take precedence)
    for key, value in dotenv_values(target).items():
        if key not in os.environ and value is not None:
            os.environ[key] = value

    return target
