<p align="center">
  <img src="docs/images/banner.png" alt="Aegra banner" />
</p>

# Aegra - Open Source LangGraph Platform Alternative

<p align="center">
  <strong>Self-hosted AI agent backend. LangGraph power without vendor lock-in.</strong>
</p>

## Fork Notice

This is a fork of [ibbybuilds/aegra](https://github.com/ibbybuilds/aegra) with custom extensions for production deployment. Original project by [Muhammad Ibrahim](https://github.com/ibbybuilds).

**Custom Extensions in This Fork:**
- **ava_v1 Agent**: LangGraph-based hotel booking agent with Redis caching and dynamic prompts
- **JWT Authentication**: Sub-1ms token validation with multi-tenant support
- **Redis Integration**: Caching layer for agent operations (hotel searches, bookings)
- **Railway Deployment**: Staging environment with automated CI/CD pipeline
- **Enhanced Documentation**: JWT auth guide, Railway deployment guide, API references

See [NOTICE](NOTICE) file for complete list of modifications.

<p align="center">
  <a href="https://github.com/lucca-mrktr/aegra/stargazers"><img src="https://img.shields.io/github/stars/lucca-mrktr/aegra" alt="GitHub stars"></a>
  <a href="https://github.com/lucca-mrktr/aegra/blob/main/LICENSE"><img src="https://img.shields.io/github/license/lucca-mrktr/aegra" alt="License"></a>
  <a href="https://github.com/lucca-mrktr/aegra/issues"><img src="https://img.shields.io/github/issues/lucca-mrktr/aegra" alt="Issues"></a>
  <a href="https://github.com/ibbybuilds/aegra"><img src="https://img.shields.io/badge/upstream-ibbybuilds%2Faegra-blue" alt="Upstream"></a>
</p>

Replace LangGraph Platform with your own infrastructure. Built with FastAPI + PostgreSQL for developers who demand complete control over their agent orchestration.

**🔌 Agent Protocol Compliant**: Implements the [Agent Protocol](https://github.com/langchain-ai/agent-protocol) specification, an open-source standard for serving LLM agents in production.

**🎯 Perfect for:** Teams escaping vendor lock-in • Data sovereignty requirements • Custom deployments • Cost optimization

## Why Aegra vs LangGraph Platform?

| Feature                | LangGraph Platform         | Aegra (Self-Hosted)                          |
| ---------------------- | -------------------------- | -------------------------------------------- |
| **Cost**               | $$$+ per month             | **Free** (infrastructure cost only)          |
| **Data Control**       | Third-party hosted         | **Your infrastructure**                      |
| **Authentication**     | Limited customization      | **Full control** (JWT/OAuth/Firebase/NoAuth) |
| **Customization**      | Platform limitations       | **Complete flexibility**                     |

## Key Features

- **Self-Hosted**: Deploy on your infrastructure with full control
- **Drop-in Replacement**: Compatible with existing LangGraph Client SDK
- **Production Ready**: PostgreSQL persistence, streaming, JWT authentication
- **Agent Protocol Compliant**: Works with [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui) and CopilotKit
- **Extensible**: Custom auth, observability (Langfuse), human-in-the-loop workflows
- **Zero Vendor Lock-in**: Apache 2.0 license, open source

## 🚀 Quick Start (5 minutes)

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL)
- uv (Python package manager)

### Get Running

```bash
# Clone and setup
git clone https://github.com/lucca-mrktr/aegra.git
cd aegra
# Install uv if missing
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync env and dependencies
uv sync

# Activate environment
source .venv/bin/activate  # Mac/Linux
# OR .venv/Scripts/activate  # Windows

# Environment
cp .env.example .env

# Start everything (database + migrations + server)
docker compose up aegra
```

### Verify It Works

```bash
# Health check
curl http://localhost:8000/health

# Interactive API docs
open http://localhost:8000/docs
```

You now have a self-hosted LangGraph Platform alternative running locally.

**💬 Agent Chat UI Compatible**: Works with [LangChain's Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui). Set `NEXT_PUBLIC_API_URL=http://localhost:8000` and `NEXT_PUBLIC_ASSISTANT_ID=agent` to connect.

## For Developers

**Guides:**
- [Developer Guide](docs/guides/developer-guide.md) - Complete setup and workflow
- [Migration Cheatsheet](docs/guides/migration-cheatsheet.md) - Quick reference

**Quick Commands:**
```bash
docker compose up aegra                                     # Start everything
python3 scripts/migrate.py upgrade                          # Apply migrations
python3 scripts/migrate.py revision --autogenerate -m "..."  # New migration
```

## Example Usage

Use the same LangGraph Client SDK:

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:8000")

# Create assistant and thread
assistant = await client.assistants.create(graph_id="agent")
thread = await client.threads.create()

# Stream responses (same API as LangGraph Platform)
async for chunk in client.runs.stream(
    thread_id=thread["thread_id"],
    assistant_id=assistant["assistant_id"],
    input={"messages": [{"type": "human", "content": "hello"}]},
):
    print(chunk)
```

Your existing LangGraph applications work without modification.

## Architecture

```text
Client → FastAPI → LangGraph → PostgreSQL
         (HTTP)   (State Mgmt)  (Storage)
```

**Stack**: FastAPI (Agent Protocol API) • LangGraph (execution) • PostgreSQL (checkpoints) • Redis (caching) • JWT Auth (multi-tenant)

## Project Structure

```text
aegra/
├── aegra.json           # Graph definitions
├── auth.py              # Authentication
├── graphs/              # Agent graphs (react_agent, ava_v1)
├── src/agent_server/    # FastAPI app
├── alembic/             # Database migrations
└── docs/                # Documentation
```

See [docs/guides/developer-guide.md](docs/guides/developer-guide.md) for details.

## Configuration

### Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

**Key variables:**
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/aegra
AUTH_TYPE=custom  # or noop
OPENAI_API_KEY=sk-...

# JWT Auth (optional)
AEGRA_JWT_SECRET=your-secret
AEGRA_JWT_ISSUER=your-issuer
AEGRA_JWT_AUDIENCE=aegra

# Redis (for ava_v1)
REDIS_HOST=localhost
REDIS_PORT=6379

# Observability (optional)
LANGFUSE_LOGGING=true
LANGFUSE_SECRET_KEY=sk-...
```

See `.env.example` for complete list.

### Graph Configuration

Define agent graphs in `aegra.json`:

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph",
    "ava_v1": "./graphs/ava_v1/graph.py:graph"
  }
}
```

## What You Get

**Core Features:**
- Agent Protocol-compliant REST API
- PostgreSQL persistence with LangGraph checkpoints
- SSE streaming with network resilience
- LangGraph Client SDK compatibility
- Human-in-the-loop workflows
- [Langfuse observability](docs/langfuse-usage.md)

**Production Features:**
- Docker + Kubernetes deployment
- Alembic database migrations
- JWT authentication (multi-tenant)
- Health checks and monitoring
- Comprehensive test suite

**Developer Experience:**
- Interactive API docs (FastAPI)
- Hot reload in development
- [Developer Guide](docs/guides/developer-guide.md)
- [Migration Cheatsheet](docs/guides/migration-cheatsheet.md)

## Contributing

Contributions welcome! You can help by:
- Reporting bugs and suggesting features
- Improving code quality and test coverage
- Enhancing documentation

See [CONTRIBUTING.md](CONTRIBUTING.md) and [good first issues](https://github.com/lucca-mrktr/aegra/labels/good%20first%20issue) to get started.

## 📄 License

Apache 2.0 License - see [LICENSE](LICENSE) file for details.

---

<p align="center">
  <strong>If this fork helps your project, please star the repo!</strong><br>
  <sub>Built with infrastructure freedom in mind</sub>
</p>
