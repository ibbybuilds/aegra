/**
 * Aegra SDK Client
 *
 * Main client for interacting with the Aegra API.
 * Compatible with LangGraph SDK patterns.
 */

import type {
  ClientConfig,
  Assistant,
  CreateAssistantOptions,
  Thread,
  CreateThreadOptions,
  StreamRunOptions,
  StreamEvent,
  APIError,
} from "./types.js";

/**
 * Main Aegra client
 */
export class AegraClient {
  private baseUrl: string;
  private headers: Record<string, string>;
  private timeout: number;

  /**
   * Assistants API
   */
  public readonly assistants: {
    create: (options: CreateAssistantOptions) => Promise<Assistant>;
    get: (assistantId: string) => Promise<Assistant>;
    list: () => Promise<Assistant[]>;
    delete: (assistantId: string) => Promise<void>;
  };

  /**
   * Threads API
   */
  public readonly threads: {
    create: (options?: CreateThreadOptions) => Promise<Thread>;
    get: (threadId: string) => Promise<Thread>;
    delete: (threadId: string) => Promise<void>;
  };

  /**
   * Runs API
   */
  public readonly runs: {
    stream: (options: StreamRunOptions) => AsyncIterable<StreamEvent>;
  };

  constructor(config: ClientConfig) {
    this.baseUrl = config.url.replace(/\/$/, ""); // Remove trailing slash
    this.timeout = config.timeout ?? 30000;

    // Setup headers
    this.headers = {
      "Content-Type": "application/json",
      ...config.headers,
    };

    if (config.apiKey) {
      this.headers["Authorization"] = `Bearer ${config.apiKey}`;
    }

    // Bind API methods
    this.assistants = {
      create: this.createAssistant.bind(this),
      get: this.getAssistant.bind(this),
      list: this.listAssistants.bind(this),
      delete: this.deleteAssistant.bind(this),
    };

    this.threads = {
      create: this.createThread.bind(this),
      get: this.getThread.bind(this),
      delete: this.deleteThread.bind(this),
    };

    this.runs = {
      stream: this.streamRun.bind(this),
    };
  }

  /**
   * Make HTTP request to Aegra API
   */
  private async request<T>(
    method: string,
    path: string,
    body?: any
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        method,
        headers: this.headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const error = await response.json().catch(() => ({
          error: response.statusText,
        })) as APIError;
        throw new Error(error.error || `HTTP ${response.status}`);
      }

      return (await response.json()) as T;
    } catch (error: any) {
      clearTimeout(timeoutId);
      if (error.name === "AbortError") {
        throw new Error(`Request timeout after ${this.timeout}ms`);
      }
      throw error;
    }
  }

  // Assistants API methods

  private async createAssistant(
    options: CreateAssistantOptions
  ): Promise<Assistant> {
    return this.request<Assistant>("POST", "/assistants", options);
  }

  private async getAssistant(assistantId: string): Promise<Assistant> {
    return this.request<Assistant>("GET", `/assistants/${assistantId}`);
  }

  private async listAssistants(): Promise<Assistant[]> {
    const response = await this.request<{ assistants: Assistant[] }>(
      "GET",
      "/assistants"
    );
    return response.assistants;
  }

  private async deleteAssistant(assistantId: string): Promise<void> {
    await this.request("DELETE", `/assistants/${assistantId}`);
  }

  // Threads API methods

  private async createThread(
    options?: CreateThreadOptions
  ): Promise<Thread> {
    return this.request<Thread>("POST", "/threads", options || {});
  }

  private async getThread(threadId: string): Promise<Thread> {
    return this.request<Thread>("GET", `/threads/${threadId}`);
  }

  private async deleteThread(threadId: string): Promise<void> {
    await this.request("DELETE", `/threads/${threadId}`);
  }

  // Runs API methods

  private async *streamRun(
    options: StreamRunOptions
  ): AsyncIterable<StreamEvent> {
    const url = `${this.baseUrl}/threads/${options.thread_id}/runs/stream`;

    const response = await fetch(url, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({
        assistant_id: options.assistant_id,
        input: options.input,
        config: options.config,
        stream_mode: options.stream_mode || ["values"],
        on_disconnect: options.on_disconnect || "cancel",
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        error: response.statusText,
      })) as APIError;
      throw new Error(error.error || `HTTP ${response.status}`);
    }

    if (!response.body) {
      throw new Error("No response body");
    }

    // Parse SSE stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent: string | null = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");

        // Keep the last incomplete line in the buffer
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            // Extract event type from SSE format
            currentEvent = line.slice(7);
          } else if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") {
              return;
            }

            try {
              const parsedData = JSON.parse(data);
              // Combine SSE event type with data payload
              const event: StreamEvent = {
                event: currentEvent as any,
                data: parsedData,
              };
              yield event;
              currentEvent = null; // Reset for next event
            } catch (e) {
              console.error("Failed to parse SSE data:", data);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
}

/**
 * Factory function to create Aegra client (LangGraph SDK compatible)
 */
export function getClient(config: ClientConfig): AegraClient {
  return new AegraClient(config);
}
