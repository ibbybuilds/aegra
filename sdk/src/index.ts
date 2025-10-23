/**
 * Aegra SDK
 *
 * TypeScript SDK for interacting with Aegra - Self-hosted LangGraph Platform Alternative
 */

export { AegraClient, getClient } from "./client.js";
export type {
  ClientConfig,
  Assistant,
  CreateAssistantOptions,
  Thread,
  CreateThreadOptions,
  StreamRunOptions,
  StreamEvent,
  Message,
  Run,
  APIError,
} from "./types.js";

// Re-export as default for convenience
export { getClient as default } from "./client.js";
