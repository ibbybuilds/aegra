"""Custom application loader for dynamic FastAPI/Starlette app imports"""

import importlib
import importlib.util
from pathlib import Path

import structlog
from starlette.applications import Starlette

logger = structlog.get_logger(__name__)


def load_custom_app(app_import: str) -> Starlette | None:
    """Load custom Starlette/FastAPI app from import path.

    Supports both file-based and module-based imports:
    - File path: "./custom_routes.py:app" or "/path/to/file.py:app"
    - Module path: "my_package.custom:app"

    Args:
        app_import: Import path in format "path/to/file.py:variable" or "module.path:variable"

    Returns:
        Loaded Starlette/FastAPI app instance or None if path is invalid

    Raises:
        ImportError: If the module or file cannot be imported
        AttributeError: If the specified variable is not found in the module
        TypeError: If the loaded object is not a Starlette/FastAPI application
    """
    logger.info(f"Loading custom app from {app_import}")

    if ":" not in app_import:
        raise ValueError(
            f"Invalid app import path format: {app_import}. "
            "Expected format: 'path/to/file.py:variable' or 'module.path:variable'"
        )

    path, name = app_import.rsplit(":", 1)

    try:
        # Determine if it's a file path or module path
        path_obj = Path(path)
        is_file_path = path_obj.is_file() or path.endswith(".py")

        if is_file_path:
            # Import from file path
            if not path_obj.exists():
                raise FileNotFoundError(f"Custom app file not found: {path}")

            spec = importlib.util.spec_from_file_location(
                "custom_app_module", str(path)
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load spec from {path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        else:
            # Import as a normal module
            module = importlib.import_module(path)

        # Get the app instance from the module
        if not hasattr(module, name):
            raise AttributeError(
                f"App '{name}' not found in module '{path}'. "
                f"Available attributes: {[attr for attr in dir(module) if not attr.startswith('_')]}"
            )

        user_app = getattr(module, name)

        # Validate it's a Starlette/FastAPI application
        if not isinstance(user_app, Starlette):
            raise TypeError(
                f"Object '{name}' in module '{path}' is not a Starlette or FastAPI application. "
                "Please initialize your app by importing and using the appropriate class:\n"
                "from starlette.applications import Starlette\n\n"
                "app = Starlette(...)\n\n"
                "or\n\n"
                "from fastapi import FastAPI\n\n"
                "app = FastAPI(...)\n\n"
            )

        logger.info(f"Successfully loaded custom app '{name}' from {path}")
        return user_app

    except ImportError as e:
        raise ImportError(f"Failed to import app module '{path}': {e}") from e
    except AttributeError as e:
        raise AttributeError(f"App '{name}' not found in module '{path}'") from e
