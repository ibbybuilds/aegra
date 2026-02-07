"""Custom application loader for dynamic FastAPI/Starlette app imports"""

import importlib
import importlib.util
from pathlib import Path

import structlog
from fastapi import FastAPI

logger = structlog.get_logger(__name__)


def load_custom_app(app_import: str, base_dir: Path | None = None) -> FastAPI | None:
    """Load custom FastAPI app from import path.

    Supports both file-based and module-based imports:
    - File path: "./custom_routes.py:app" or "/path/to/file.py:app"
    - Module path: "my_package.custom:app"

    Args:
        app_import: Import path in format "path/to/file.py:variable" or "module.path:variable"
        base_dir: Base directory for resolving relative file paths (e.g., config file directory)

    Returns:
        Loaded FastAPI app instance or None if path is invalid

    Raises:
        ImportError: If the module or file cannot be imported
        AttributeError: If the specified variable is not found in the module
        TypeError: If the loaded object is not a FastAPI application
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
        is_file_path = path_obj.suffix == ".py" or path.startswith("./") or path.startswith("../")

        if is_file_path:
            # Resolve relative paths from base_dir if provided
            if not path_obj.is_absolute() and base_dir is not None:
                path_obj = (base_dir / path_obj).resolve()

            # Import from file path
            if not path_obj.exists():
                raise FileNotFoundError(f"Custom app file not found: {path_obj}")

            spec = importlib.util.spec_from_file_location("custom_app_module", str(path_obj))
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load spec from {path_obj}")

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

        # Validate it's a FastAPI application
        if not isinstance(user_app, FastAPI):
            raise TypeError(
                f"Object '{name}' in module '{path}' is not a FastAPI application. "
                "Custom apps must be FastAPI instances for proper OpenAPI support.\n"
                "Please initialize your app using:\n\n"
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n\n"
            )

        logger.info(f"Successfully loaded custom app '{name}' from {path}")
        return user_app

    except ImportError as e:
        raise ImportError(f"Failed to import app module '{path}': {e}") from e
    except AttributeError as e:
        raise AttributeError(f"App '{name}' not found in module '{path}'") from e
