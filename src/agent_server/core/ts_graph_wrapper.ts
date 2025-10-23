/**
 * TypeScript Graph Wrapper
 *
 * This script executes TypeScript/JavaScript LangGraph graphs from Python.
 * It handles:
 * - Loading the graph from a file
 * - Connecting to PostgreSQL for state persistence
 * - Executing the graph with provided input
 * - Streaming results back to Python via JSON lines
 */

import { readFile } from "fs/promises";
import { resolve } from "path";

interface ExecutionContext {
  graph_path: string;
  export_name: string;
  input: Record<string, any>;
  config: Record<string, any>;
  database_url: string;
}

/**
 * Stream an event to Python via stdout as a JSON line
 */
function streamEvent(event: Record<string, any>): void {
  console.log(JSON.stringify(event));
}

/**
 * Load and execute a TypeScript graph
 */
async function executeGraph(context: ExecutionContext): Promise<void> {
  try {
    // Load the graph module dynamically
    const graphModule = await import(context.graph_path);
    const graph = graphModule[context.export_name];

    if (!graph) {
      throw new Error(
        `Export '${context.export_name}' not found in ${context.graph_path}`
      );
    }

    // Initialize PostgreSQL checkpointer
    // This uses the same tables as Python graphs for state persistence
    let compiledGraph = graph;

    // Check if we need to set up checkpointer
    if (context.database_url) {
      try {
        // Import PostgreSQL checkpointer
        const { PostgresSaver } = await import(
          "@langchain/langgraph-checkpoint-postgres"
        );

        // Create checkpointer connection
        const checkpointer = PostgresSaver.fromConnString(context.database_url);
        await checkpointer.setup();

        // Compile graph with checkpointer if not already compiled
        if (typeof graph.compile === "function") {
          compiledGraph = graph.compile({ checkpointer });
        } else if (graph.withConfig) {
          // Already compiled, add checkpointer
          compiledGraph = graph.withConfig({ checkpointer });
        }
      } catch (error: any) {
        console.error(
          `Warning: Could not set up PostgreSQL checkpointer: ${error.message}`
        );
        // Continue without checkpointer
      }
    }

    // Execute the graph and stream results
    const stream = await compiledGraph.stream(context.input, context.config);

    for await (const event of stream) {
      // Stream events directly without wrapping
      // This matches LangGraph's native Python streaming format
      streamEvent(event);
    }
  } catch (error: any) {
    // Send error event
    streamEvent({
      type: "error",
      data: {
        message: error.message,
        stack: error.stack,
      },
    });
    process.exit(1);
  }
}

/**
 * Main entry point
 */
async function main(): void {
  try {
    // Read context from command line argument (JSON file path)
    const contextPath = process.argv[2];
    if (!contextPath) {
      throw new Error("Context file path not provided");
    }

    const contextJson = await readFile(contextPath, "utf-8");
    const context: ExecutionContext = JSON.parse(contextJson);

    await executeGraph(context);
  } catch (error: any) {
    console.error(`Fatal error: ${error.message}`);
    process.exit(1);
  }
}

main();
