# Aegra Streaming Architecture

## Current: Unified Broker with Replay (v0.9)

### Normal Flow (same instance)

```mermaid
flowchart LR
    C[Client] -->|1. POST /runs| LB[Load Balancer]
    LB -->|routes to| A[Instance A]
    A -->|2. executes graph| A
    A -->|3. SSE stream| C
```

### Reconnect Flow (cross-instance, Redis enabled)

```mermaid
flowchart TD
    C[Client] -->|1. SSE drops, reconnects| LB[Load Balancer]
    LB -->|2. routes to| B[Instance B]
    B -->|3. replay from Redis Lists| R[(Redis)]
    B -->|4. subscribe live events| R
    A[Instance A] -->|still executing, publishing| R

    style C fill:#f5c542,stroke:#f5c542,color:#000
    style LB fill:#a78bfa,stroke:#a78bfa,color:#000
    style A fill:#60a5fa,stroke:#60a5fa,color:#000
    style B fill:#60a5fa,stroke:#60a5fa,color:#000
    style R fill:#f87171,stroke:#f87171,color:#000
```

### How SSE Reconnect Works

1. Client connects to **Instance A**, receives events `evt-1`, `evt-2`, `evt-3`
2. Connection drops (network blip, timeout, etc.)
3. Client sends **new HTTP request** with `Last-Event-ID: evt-3` header
4. Load balancer routes to **Instance B**
5. Instance B replays missed events from the **broker's replay buffer** (Redis Lists when Redis enabled, in-memory list otherwise)
6. Instance B subscribes to **Redis Pub/Sub** channel for live events from Instance A

### Broker Backends

| Feature | In-Memory (`aegra dev`) | Redis (`aegra up`) |
|---------|------------------------|-------------------|
| Live streaming | asyncio.Queue | Redis Pub/Sub |
| Replay buffer | Python list | Redis Lists (RPUSH/LRANGE) |
| Cross-instance | No | Yes |
| Replay TTL | Process lifetime | 1 hour |
| Config | `REDIS_BROKER_ENABLED=false` | `REDIS_BROKER_ENABLED=true` |

### Dev vs Production

- **`aegra dev`** starts only PostgreSQL via Docker, runs uvicorn directly. Uses the in-memory broker — no Redis needed. SSE replay works on a single instance via a Python list.
- **`aegra up`** starts the full stack (PostgreSQL + Redis + API) via Docker Compose. The compose file sets `REDIS_BROKER_ENABLED=true` automatically, so Redis pub/sub and replay are active without any manual config.

## Future: Distributed Workers

```mermaid
flowchart TD
    C[Client] -->|SSE Stream| LB[Load Balancer]
    LB --> API_A[API Instance A]
    LB --> API_B[API Instance B]
    API_A -->|enqueue job| R[(Redis Streams)]
    R -->|dequeue| W1[Worker 1]
    R -->|dequeue| W2[Worker 2]
    W1 -->|publish events| RP[(Redis Pub/Sub)]
    W2 -->|publish events| RP
    RP -->|subscribe| API_A
    RP -->|subscribe| API_B

    style C fill:#f5c542,stroke:#f5c542,color:#000
    style LB fill:#a78bfa,stroke:#a78bfa,color:#000
    style API_A fill:#fb923c,stroke:#fb923c,color:#000
    style API_B fill:#fb923c,stroke:#fb923c,color:#000
    style R fill:#f87171,stroke:#f87171,color:#000
    style RP fill:#f87171,stroke:#f87171,color:#000
    style W1 fill:#4ade80,stroke:#4ade80,color:#000
    style W2 fill:#4ade80,stroke:#4ade80,color:#000
```
