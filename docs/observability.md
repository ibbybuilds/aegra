````markdown
# Unified Observability & Tracing

Aegra utilizes a **Unified OpenTelemetry (OTEL) Architecture** for observability. This allows you to avoid vendor lock-in and stream traces to multiple backends simultaneously ("fan-out") without changing your code.

## Supported Targets

Out of the box, Aegra supports:

- **Langfuse** (Native integration via OTLP)
- **Arize Phoenix** (Great for local debugging and evaluation)
- **Generic OTLP** (Any compatible backend: Jaeger, Honeycomb, Datadog, etc.)

## Configuration

Tracing is configured via environment variables in your `.env` file.

### 1. Enable Tracing

Set the `OTEL_TARGETS` variable to a comma-separated list of providers you want to enable.

```bash
# Enable both Langfuse and Phoenix
OTEL_TARGETS="LANGFUSE,PHOENIX"

# Enable only Generic OTLP
OTEL_TARGETS="GENERIC"

# Disable all tracing
OTEL_TARGETS=""
```
You can also enable console logging for debugging:
```bash
OTEL_CONSOLE_EXPORT=true
```

### 2. Provider Specifics

#### Langfuse Configuration

Aegra uses the standard OTLP endpoint for Langfuse.

```bash
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

#### Arize Phoenix Configuration

Phoenix is excellent for local trace visualization.

```bash
# Default local Phoenix endpoint
PHOENIX_COLLECTOR_ENDPOINT=http://127.0.0.1:6006/v1/traces
PHOENIX_API_KEY=  # Optional
```

#### Generic OTLP Configuration

Connect to Jaeger, Honeycomb, or any OTLP collector.

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318/v1/traces
# Optional headers (comma separated)
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <token>,X-Custom=Value"
```


### Architecture

Aegra uses a "Pure OTEL" approach:

1. Auto-Instrumentation: Uses openinference-instrumentation-langchain to automatically capture LangGraph steps.
2. Singleton Provider: Initialized once during application startup.
3. Fan-out: Uses BatchSpanProcessor to send the same trace data to multiple configured exporters efficiently.

This ensures low overhead and maximum compatibility with the observability ecosystem.
