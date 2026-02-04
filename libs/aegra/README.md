# aegra

**Aegra** is an open-source, self-hosted alternative to LangGraph Platform.

This is a meta-package that installs the complete Aegra stack:
- **aegra-cli**: Command-line interface for managing deployments
- **aegra-api**: Core API server implementing the Agent Protocol

## Installation

```bash
pip install aegra
```

## Quick Start

```bash
# Initialize a new project with Docker support
aegra init --docker

# Start PostgreSQL
aegra up postgres

# Apply database migrations
aegra db upgrade

# Start development server
aegra dev
```

## Features

- **Drop-in Replacement**: Compatible with the LangGraph SDK
- **Self-Hosted**: Run on your own PostgreSQL database
- **Agent Protocol Compliant**: Works with Agent Chat UI, LangGraph Studio, CopilotKit
- **Streaming Support**: Real-time streaming of agent responses
- **Human-in-the-Loop**: Built-in support for human approval workflows

## Documentation

For full documentation, visit the [GitHub repository](https://github.com/ibbybuilds/aegra).

## Related Packages

- [aegra-cli](https://pypi.org/project/aegra-cli/): CLI for project management
- [aegra-api](https://pypi.org/project/aegra-api/): Core API server
