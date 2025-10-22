/**
 * Example TypeScript LangGraph Agent
 *
 * This is a simple chatbot agent that demonstrates TypeScript graph
 * integration with Aegra. It maintains conversation state and responds
 * to user messages.
 */

import { StateGraph, Annotation } from "@langchain/langgraph";
import type { RunnableConfig } from "@langchain/core/runnables";

/**
 * Define the state structure for the agent
 */
const StateAnnotation = Annotation.Root({
  messages: Annotation<Array<{ role: string; content: string }>>({
    reducer: (left, right) => left.concat(right),
    default: () => [],
  }),
});

/**
 * Main node that handles message processing
 */
async function callModel(
  state: typeof StateAnnotation.State,
  config: RunnableConfig
): Promise<typeof StateAnnotation.Update> {
  const messages = state.messages;
  const lastMessage = messages[messages.length - 1];

  // Simple response logic (replace with actual LLM call in production)
  const response = {
    role: "assistant",
    content: `Hello! You said: "${lastMessage?.content}". I'm a TypeScript-powered agent running in Aegra!`,
  };

  return {
    messages: [response],
  };
}

/**
 * Router function to determine if we should continue or end
 */
function shouldContinue(
  state: typeof StateAnnotation.State
): "__end__" | "callModel" {
  // Simple logic: end after one exchange
  if (state.messages.length > 1) {
    return "__end__";
  }
  return "callModel";
}

/**
 * Build and export the graph
 */
const workflow = new StateGraph(StateAnnotation)
  .addNode("callModel", callModel)
  .addEdge("__start__", "callModel")
  .addConditionalEdges("callModel", shouldContinue);

// Export the compiled graph
export const graph = workflow.compile();

// Set graph metadata
graph.name = "TypeScript Example Agent";
