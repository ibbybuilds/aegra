# Dependencies Configuration

Aegra supports the `dependencies` configuration key for adding shared utility modules to the Python path, matching LangGraph CLI behavior.

## Overview

When your graphs need to import from shared utility modules that aren't installed as packages, you can use the `dependencies` config to add those paths to `sys.path` before graphs are loaded.

## Configuration

Add the `dependencies` array to your `aegra.json`:

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  },
  "dependencies": [
    "./shared",
    "./libs/common"
  ]
}
```

### Path Resolution

- **Relative paths** are resolved from the config file's directory
- **Absolute paths** are used as-is
- Paths are added to `sys.path` in order (first dependency has highest priority)
- Non-existent paths generate a warning but don't cause failure

## Use Case Example

### Project Structure

```
my-project/
├── aegra.json
├── graphs/
│   └── my_agent/
│       └── graph.py      # Imports from shared/
├── shared/
│   ├── __init__.py
│   ├── utils.py          # Shared utilities
│   └── prompts.py        # Shared prompt templates
└── libs/
    └── custom_tools/
        └── __init__.py   # Custom tool definitions
```

### Configuration

```json
{
  "graphs": {
    "my_agent": "./graphs/my_agent/graph.py:graph"
  },
  "dependencies": [
    "./shared",
    "./libs/custom_tools"
  ]
}
```

### Graph Code

```python
# graphs/my_agent/graph.py

# These imports work because dependencies are in sys.path
from utils import format_response
from prompts import SYSTEM_PROMPT
from custom_tools import MyCustomTool

# ... rest of graph definition
```

## Behavior

1. Dependencies are loaded during `LangGraphService.initialize()`
2. Paths are added to `sys.path` before any graphs are loaded
3. First dependency in the config has highest priority in import resolution
4. Missing paths log a warning but don't prevent startup

## Logging

When dependencies are configured, you'll see log messages like:

```
INFO: Added dependency path to sys.path: /app/shared
INFO: Added dependency path to sys.path: /app/libs/custom_tools
```

If a path doesn't exist:

```
WARNING: Dependency path does not exist: /app/missing_path
```

## Compatibility

This configuration is compatible with LangGraph CLI's `dependencies` config, making it easy to migrate projects between platforms.
