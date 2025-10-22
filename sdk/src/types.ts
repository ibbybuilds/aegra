/**
 * Type definitions for Aegra SDK
 *
 * These types match the Agent Protocol specification and Aegra's API.
 */

/**
 * Assistant definition
 */
export interface Assistant {
  assistant_id: string;
  name: string;
  description?: string;
  graph_id: string;
  config?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

/**
 * Thread definition
 */
export interface Thread {
  thread_id: string;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, any>;
}

/**
 * Run definition
 */
export interface Run {
  run_id: string;
  thread_id: string;
  assistant_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, any>;
}

/**
 * Message format
 */
export interface Message {
  role: "human" | "assistant" | "system";
  content: string | Array<{ type: string; text?: string; [key: string]: any }>;
  metadata?: Record<string, any>;
}

/**
 * Stream event types
 */
export type StreamEvent =
  | {
      event: "values";
      data: any;
    }
  | {
      event: "messages-tuple";
      data: [string, Message];
    }
  | {
      event: "custom";
      data: any;
    }
  | {
      event: "end";
      data?: any;
    }
  | {
      event: "error";
      data: {
        message: string;
        stack?: string;
      };
    };

/**
 * Client configuration
 */
export interface ClientConfig {
  /** Base URL of Aegra server */
  url: string;

  /** API key for authentication (optional) */
  apiKey?: string;

  /** Default headers to include in all requests */
  headers?: Record<string, string>;

  /** Request timeout in milliseconds */
  timeout?: number;
}

/**
 * Create assistant options
 */
export interface CreateAssistantOptions {
  graph_id: string;
  name?: string;
  description?: string;
  config?: Record<string, any>;
  if_exists?: "do_nothing" | "update" | "error";
}

/**
 * Create thread options
 */
export interface CreateThreadOptions {
  metadata?: Record<string, any>;
}

/**
 * Stream run options
 */
export interface StreamRunOptions {
  thread_id: string;
  assistant_id: string;
  input: {
    messages: Message[];
  };
  config?: Record<string, any>;
  stream_mode?: Array<"values" | "messages-tuple" | "custom">;
  on_disconnect?: "cancel" | "continue";
}

/**
 * Error response from API
 */
export interface APIError {
  error: string;
  details?: any;
}
