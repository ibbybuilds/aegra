# Observability Configuration

Aegra supports a **generic, configuration-driven observability layer** using OpenTelemetry (OTEL). You can send traces to any OTLP-compatible backend without vendor-specific code changes.

## Quick Start

Configure exporters via `aegra.json` or environment variables.

### Option 1: `aegra.json`

```json
{
  "observability": {
    "exporters": {
      "my-backend": {
        "endpoint": "http://localhost:4318/v1/traces",
        "headers": {
          "Authorization": "Bearer your-token"
        }
      }
    }
  }
}
```

### Option 2: Environment Variable

```bash
export OTEL_EXPORTERS='{"my-backend": {"endpoint": "http://localhost:4318/v1/traces"}}'
```

---

## Provider Examples

### Arize Phoenix (Local Development)

[Phoenix](https://github.com/Arize-ai/phoenix) is an open-source observability tool for LLM applications.

**1. Start Phoenix:**
```bash
pip install arize-phoenix
phoenix serve
```

**2. Configure `aegra.json`:**
```json
{
  "observability": {
    "exporters": {
      "local-phoenix": {
        "endpoint": "http://localhost:6006/v1/traces"
      }
    }
  }
}
```

**3. View traces:** Open http://localhost:6006

---

### MLflow (Experiment Tracking)

[MLflow](https://mlflow.org/) supports OTLP tracing for experiment tracking.

**1. Start MLflow:**
```bash
pip install mlflow
mlflow server --host 0.0.0.0 --port 5000
```

**2. Configure `aegra.json`:**
```json
{
  "observability": {
    "exporters": {
      "mlflow": {
        "endpoint": "http://localhost:5000/v1/traces",
        "headers": {
          "x-mlflow-experiment-id": "0"
        }
      }
    }
  }
}
```

> **Note:** Set `x-mlflow-experiment-id` to your target experiment ID.

---

### Jaeger (Distributed Tracing)

[Jaeger](https://www.jaegertracing.io/) is a popular open-source distributed tracing system.

**1. Start Jaeger:**
```bash
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

**2. Configure `aegra.json`:**
```json
{
  "observability": {
    "exporters": {
      "jaeger": {
        "endpoint": "http://localhost:4318/v1/traces"
      }
    }
  }
}
```

**3. View traces:** Open http://localhost:16686

---

### Honeycomb (Production Observability)

[Honeycomb](https://www.honeycomb.io/) is a cloud observability platform.

**1. Get your API key from Honeycomb dashboard.**

**2. Configure `aegra.json`:**
```json
{
  "observability": {
    "exporters": {
      "honeycomb": {
        "endpoint": "https://api.honeycomb.io/v1/traces",
        "headers": {
          "x-honeycomb-team": "YOUR_API_KEY",
          "x-honeycomb-dataset": "aegra-traces"
        }
      }
    }
  }
}
```

---

### Grafana Tempo

[Grafana Tempo](https://grafana.com/oss/tempo/) is a distributed tracing backend.

**1. Configure `aegra.json`:**
```json
{
  "observability": {
    "exporters": {
      "tempo": {
        "endpoint": "http://tempo:4318/v1/traces"
      }
    }
  }
}
```

---

## Multiple Exporters (Fan-out)

You can configure multiple exporters to send traces to multiple backends simultaneously:

```json
{
  "observability": {
    "exporters": {
      "local-phoenix": {
        "endpoint": "http://localhost:6006/v1/traces"
      },
      "production-honeycomb": {
        "endpoint": "https://api.honeycomb.io/v1/traces",
        "headers": {
          "x-honeycomb-team": "YOUR_API_KEY"
        }
      }
    }
  }
}
```

---

## Legacy Langfuse Support

Existing Langfuse users can continue using the callback-based approach:

```bash
export LANGFUSE_LOGGING=true
export LANGFUSE_PUBLIC_KEY=your-public-key
export LANGFUSE_SECRET_KEY=your-secret-key
export LANGFUSE_HOST=https://cloud.langfuse.com
```

This works alongside the new OTLP exporters without conflict.

---

## Migration Guide

### Migrating from Langfuse Callbacks to OTEL

If you want to use the new unified OTEL approach for Langfuse:

1. **Disable legacy callbacks:**
   ```bash
   export LANGFUSE_LOGGING=false
   ```

2. **Configure via OTLP:**
   ```json
   {
     "observability": {
       "exporters": {
         "langfuse": {
           "endpoint": "https://cloud.langfuse.com/api/public/otel/v1/traces",
           "headers": {
             "Authorization": "Basic <base64(public_key:secret_key)>"
           }
         }
       }
     }
   }
   ```

   > **Note:** For US region, use `https://us.cloud.langfuse.com/api/public/otel/v1/traces`

> ⚠️ **Warning:** Do not enable both legacy Langfuse callbacks (`LANGFUSE_LOGGING=true`) AND an OTLP exporter pointing to Langfuse at the same time. This will cause trace duplication.
