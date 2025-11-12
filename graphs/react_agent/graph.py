"""Define a custom Reasoning and Action agent.

Works with a chat model with tool calling support.
"""

from datetime import UTC, datetime
from typing import Literal, cast

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from react_agent.context import Context
from react_agent.file_processor import process_multimodal_content
from react_agent.state import InputState, State
from react_agent.tools import TOOLS
from react_agent.utils import load_chat_model

# Define the function that calls the model


async def call_model(
    state: State, runtime: Runtime[Context]
) -> dict[str, list[AIMessage]]:
    """Call the LLM powering our "agent".

    This function prepares the prompt, initializes the model, and processes the response.

    Args:
        state (State): The current state of the conversation.
        config (RunnableConfig): Configuration for the model run.

    Returns:
        dict: A dictionary containing the model's response message.
    """
    # Initialize the model with tool binding. Change the model or add more tools here.
    model = load_chat_model(runtime.context.model).bind_tools(TOOLS)

    # Format the system prompt. Customize this to change the agent's behavior.
    system_message = runtime.context.system_prompt.format(
        system_time=datetime.now(tz=UTC).isoformat()
    )

    # Process messages to extract file content from multimodal messages
    # Only process the last message if it contains files to avoid re-processing
    processed_messages = []
    messages_to_process = state.messages

    # Check if last message needs processing (has multimodal content)
    if (
        messages_to_process
        and isinstance(messages_to_process[-1], HumanMessage)
        and isinstance(messages_to_process[-1].content, list)
    ):
        # Process only the new message with files
        last_msg = messages_to_process[-1]
        text_content = process_multimodal_content(last_msg.content)
        processed_last = HumanMessage(content=text_content, id=last_msg.id)

        # Use all previous messages as-is, only replace the last one
        processed_messages = messages_to_process[:-1] + [processed_last]
    else:
        # No file processing needed
        processed_messages = messages_to_process

    # Get the model's response
    response = cast(
        "AIMessage",
        await model.ainvoke(
            [{"role": "system", "content": system_message}, *processed_messages]
        ),
    )

    # Handle the case when it's the last step and the model still wants to use a tool
    if state.is_last_step and response.tool_calls:
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content="Sorry, I could not find an answer to your question in the specified number of steps.",
                )
            ]
        }

    # Return the model's response as a list to be added to existing messages
    return {"messages": [response]}


# Tool call limits per tool per run
TOOL_CALL_LIMITS = {
    "get_student_ai_mentor_onboarding": 1,  # Limit this expensive tool to 1 call per run
}


async def call_tools_with_limit(state: State) -> dict:
    """
    Execute tools while enforcing per-run call limits.

    Some tools (like get_student_ai_mentor_onboarding) return large amounts of data
    and should only be called once per conversation run to avoid:
    - Excessive API calls
    - Token bloat
    - Performance issues

    This function checks tool_call_counts in state and either:
    - Executes the tool if under the limit
    - Returns an error message if the limit is exceeded
    """
    import logging

    logger = logging.getLogger(__name__)

    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []}

    logger.info(f"[TOOL LIMIT] Processing {len(last_message.tool_calls)} tool call(s)")
    for tc in last_message.tool_calls:
        logger.info(f"[TOOL LIMIT]   - {tc.get('name')}")

    tool_call_counts = state.tool_call_counts.copy()
    logger.info(f"[TOOL LIMIT] Current state counts: {tool_call_counts}")

    messages_to_add = []
    tools_to_execute = []

    # Check each tool call against limits
    # NOTE: If AI requests the same tool multiple times in parallel,
    # we increment the counter for each request in this loop
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        limit = TOOL_CALL_LIMITS.get(tool_name)

        if limit is not None:
            # Get the CURRENT count from our local copy (updated in this loop for parallel calls)
            current_count = tool_call_counts.get(tool_name, 0)
            logger.info(
                f"[TOOL LIMIT] {tool_name}: count={current_count}, limit={limit}"
            )

            # Check if we've already hit the limit
            if current_count >= limit:
                # Limit exceeded - return error message
                logger.warning(
                    f"[TOOL LIMIT] BLOCKED: {tool_name} (count={current_count} >= limit={limit})"
                )
                messages_to_add.append(
                    ToolMessage(
                        content=f"Error: The tool '{tool_name}' can only be called {limit} time(s) per run. "
                        f"It has already been called or requested {current_count} time(s) in this conversation. "
                        f"Please use the information from the previous call instead of calling the tool again.",
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                    )
                )
            else:
                # Under limit - allow execution and increment counter IMMEDIATELY
                # This prevents duplicate parallel calls to the same tool
                logger.info(
                    f"[TOOL LIMIT] ALLOWED: {tool_name} (incrementing count to {current_count + 1})"
                )
                tools_to_execute.append(tool_call)
                tool_call_counts[tool_name] = current_count + 1
        else:
            # No limit for this tool - execute normally (don't track count)
            logger.info(f"[TOOL LIMIT] NO LIMIT: {tool_name}")
            tools_to_execute.append(tool_call)

    # Execute allowed tools
    if tools_to_execute:
        # Create a temporary message with only the allowed tool calls
        temp_message = AIMessage(
            content=last_message.content,
            tool_calls=tools_to_execute,
        )
        temp_state = State(
            messages=[*state.messages[:-1], temp_message],
            is_last_step=state.is_last_step,
            tool_call_counts=state.tool_call_counts,  # Use original state, will update below
        )

        # Use the standard ToolNode to execute
        tool_node = ToolNode(TOOLS)
        result = await tool_node.ainvoke(temp_state)
        messages_to_add.extend(result.get("messages", []))

    # Return updated messages AND updated counters
    return {
        "messages": messages_to_add,
        "tool_call_counts": tool_call_counts,
    }


# Define a new graph

builder = StateGraph(State, input_schema=InputState, context_schema=Context)

# Define the two nodes we will cycle between
builder.add_node(call_model)
builder.add_node("tools", call_tools_with_limit)

# Set the entrypoint as `call_model`
# This means that this node is the first one called
builder.add_edge("__start__", "call_model")


def route_model_output(state: State) -> Literal["__end__", "tools"]:
    """Determine the next node based on the model's output.

    This function checks if the model's last message contains tool calls.

    Args:
        state (State): The current state of the conversation.

    Returns:
        str: The name of the next node to call ("__end__" or "tools").
    """
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        raise ValueError(
            f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
        )
    # If there is no tool call, then we finish
    if not last_message.tool_calls:
        return "__end__"
    # Otherwise we execute the requested actions
    return "tools"


# Add a conditional edge to determine the next step after `call_model`
builder.add_conditional_edges(
    "call_model",
    # After call_model finishes running, the next node(s) are scheduled
    # based on the output from route_model_output
    route_model_output,
)

# Add a normal edge from `tools` to `call_model`
# This creates a cycle: after using tools, we always return to the model
builder.add_edge("tools", "call_model")

# Compile the builder into an executable graph
graph = builder.compile(name="ReAct Agent")
