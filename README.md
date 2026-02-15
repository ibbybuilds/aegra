<p align="center">
  <img src="docs/images/banner.png" alt="Aegra banner" />
</p>

<h1 align="center">Aegra</h1>

<p align="center">
  <strong>Self-hosted LangGraph Platform alternative. Your infrastructure, your rules.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/aegra-api/"><img src="https://img.shields.io/pypi/v/aegra-api?label=aegra-api&color=blue" alt="PyPI API"></a>
  <a href="https://pypi.org/project/aegra-cli/"><img src="https://img.shields.io/pypi/v/aegra-cli?label=aegra-cli&color=blue" alt="PyPI CLI"></a>
  <a href="https://github.com/ibbybuilds/aegra/actions/workflows/ci.yml"><img src="https://github.com/ibbybuilds/aegra/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://app.codecov.io/gh/ibbybuilds/aegra"><img src="https://codecov.io/gh/ibbybuilds/aegra/graph/badge.svg" alt="Codecov"></a>
</p>

<p align="center">
  <a href="https://github.com/ibbybuilds/aegra/stargazers"><img src="https://img.shields.io/github/stars/ibbybuilds/aegra" alt="GitHub stars"></a>
  <a href="https://github.com/ibbybuilds/aegra/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ibbybuilds/aegra" alt="License"></a>
  <a href="https://discord.com/invite/D5M3ZPS25e"><img src="https://img.shields.io/badge/Discord-Join-7289DA?logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://patreon.com/aegra"><img src="https://img.shields.io/badge/Sponsor-EA4AAA?logo=github-sponsors&logoColor=white" alt="Sponsor"></a>
</p>

---

Aegra is a drop-in replacement for LangGraph Platform. Use the same LangGraph SDK, same APIs, but run it on your own infrastructure with PostgreSQL persistence.

**Works with:** [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui) | [LangGraph Studio](https://github.com/langchain-ai/langgraph-studio) | [AG-UI / CopilotKit](https://github.com/CopilotKit/CopilotKit)

## 🚀 Quick Start

### Using the CLI (Recommended)

**Prerequisites:** Python 3.11+, Docker (for PostgreSQL)

```bash
pip install aegra-cli

# Initialize a new project — prompts for location, template, and name
aegra init

# Follow the printed next steps:
cd <your-project>
cp .env.example .env     # Add your OPENAI_API_KEY to .env
uv sync                  # Install dependencies
uv run aegra dev         # Start PostgreSQL + dev server
```

> **Note:** Always install `aegra-cli` directly — not the `aegra` meta-package. The `aegra` package on PyPI is a convenience wrapper that does not support version pinning.

### From Source

```bash
git clone https://github.com/ibbybuilds/aegra.git
cd aegra
cp .env.example .env
# Add your OPENAI_API_KEY to .env

docker compose up
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) to explore the API.

Your existing LangGraph code works without changes:

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:8000")

assistant = await client.assistants.create(graph_id="agent")
thread = await client.threads.create()

async for chunk in client.runs.stream(
    thread_id=thread["thread_id"],
    assistant_id=assistant["assistant_id"],
    input={"messages": [{"type": "human", "content": "Hello!"}]},
):
    print(chunk)
```

## 🔥 Why Aegra?

| Feature | LangGraph Platform | Aegra |
|:--|:--|:--|
| **Cost** | $$$+ per month | Free (self-hosted) |
| **Data Control** | Third-party hosted | Your infrastructure |
| **Vendor Lock-in** | High dependency | Zero lock-in |
| **Authentication** | Limited options | Custom (JWT/OAuth/Firebase) |
| **Database** | Managed, no BYO | Bring your own Postgres |
| **Tracing** | LangSmith only | Your choice (Langfuse, etc.) |
| **SDK Compatibility** | LangGraph SDK | Same LangGraph SDK |

## ✨ Features

- **[Agent Protocol](https://github.com/langchain-ai/agent-protocol) compliant** - Works with Agent Chat UI, LangGraph Studio, CopilotKit
- **[Human-in-the-loop](docs/developer-guide.md)** - Approval gates and user intervention points
- **[Streaming](docs/developer-guide.md)** - Real-time responses with network resilience
- **[Persistent state](docs/developer-guide.md)** - PostgreSQL checkpoints via LangGraph
- **[Configurable auth](docs/developer-guide.md)** - JWT, OAuth, Firebase, or none
- **[Unified Observability](docs/observability.md)** - Fan-out tracing support via OpenTelemetry
- **[Semantic store](docs/semantic-store.md)** - Vector embeddings with pgvector
- **[Custom routes](docs/custom-routes.md)** - Add your own FastAPI endpoints

## 🛠️ CLI Commands

```bash
aegra init              # Interactive — asks for location, template, and name
aegra init ./my-agent   # Create at path (still prompts for template)

aegra dev               # Start development server (hot reload + auto PostgreSQL)
aegra serve             # Start production server (no reload)
aegra up                # Build and start all Docker services
aegra down              # Stop Docker services

aegra version           # Show version info
```

## 📚 Documentation

| Topic | Description |
|-------|-------------|
| [Configuration](docs/configuration.md) | aegra.json format and environment variables |
| [Developer Guide](docs/developer-guide.md) | Local setup, migrations, development workflow |
| [Authentication & Authorization](docs/authentication.md) | Configure JWT, OAuth, or custom auth with fine-grained access control |
| [Custom Routes](docs/custom-routes.md) | Add your own FastAPI endpoints |
| [Semantic Store](docs/semantic-store.md) | Vector embeddings with pgvector |
| [Dependencies](docs/dependencies.md) | Shared modules for graph imports |
| [Observability & Tracing](docs/observability.md) | Configure Langfuse, Phoenix, and generic OTLP exporters |
| [Production Setup](docs/production-docker-setup.md) | Docker deployment for production |

> ⚠️ **Upgrading from an older version?** See the [PostgreSQL 18 Migration Guide](docs/postgres-18-migration.md).

## 💬 Community & Support

- **[Discord](https://discord.com/invite/D5M3ZPS25e)** - Chat with the community
- **[GitHub Discussions](https://github.com/ibbybuilds/aegra/discussions)** - Ask questions, share ideas
- **[GitHub Issues](https://github.com/ibbybuilds/aegra/issues)** - Report bugs

## 🏗️ Built With

- [FastAPI](https://fastapi.tiangolo.com/) - HTTP layer
- [LangGraph](https://github.com/langchain-ai/langgraph) - State management & graph execution
- [PostgreSQL](https://www.postgresql.org/) - Persistence & checkpoints
- [OpenTelemetry](https://opentelemetry.io/) - Observability standard
- [pgvector](https://github.com/pgvector/pgvector) - Vector embeddings

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) and check out [good first issues](https://github.com/ibbybuilds/aegra/labels/good%20first%20issue).

## 💖 Support the Project

The best contribution is code, PRs, and bug reports - that's what makes open source thrive.

For those who want to support Aegra financially, whether you're using it in production or just believe in what we're building, you can [become a sponsor](https://patreon.com/aegra). Sponsorships help keep development active and the project healthy.

## 📄 License

Apache 2.0 - see [LICENSE](LICENSE).

---

<p align="center">
  <strong>⭐ Star us if Aegra helps you escape vendor lock-in ⭐</strong>
</p>

<a href="https://www.star-history.com/#ibbybuilds/aegra&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=ibbybuilds/aegra&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=ibbybuilds/aegra&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=ibbybuilds/aegra&type=Date" />
  </picture>
</a>
