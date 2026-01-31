# Langfuse Integration for Observability

Aegra includes a plug-and-play integration for [Langfuse](https://langfuse.com/) to provide detailed tracing and observability for your LangGraph runs. When enabled, every graph execution will be traced, and the logs will be sent to your Langfuse project.

## Enabling Langfuse

To enable Langfuse, you need to configure a few environment variables. The recommended way to do this is by creating a `.env` file in the root of your project and adding the following key-value pairs.

1.  **Enable the Integration**: Set the following variable to `true` in your `.env` file.
    ```env
    LANGFUSE_LOGGING=true
    ```

2.  **Configure Langfuse Credentials**: You'll also need to provide your Langfuse project credentials. These can be found in your Langfuse project settings. You can use [Langfuse Cloud](https://cloud.langfuse.com) or a self-hosted instance.
    ```env
    LANGFUSE_PUBLIC_KEY="pk-lf-..."
    LANGFUSE_SECRET_KEY="sk-lf-..."
    LANGFUSE_HOST="https://cloud.langfuse.com" # Or your self-hosted instance
    ```

3.  **Install the Langfuse Package**: The integration requires the `langfuse` Python package to be installed.
    ```bash
    pip install langfuse
    ```
    If `LANGFUSE_LOGGING` is enabled but the package is not installed, Aegra will log a warning and continue without tracing.

## Traced Metadata

The integration is designed to be zero-config. Once enabled, it will automatically capture and send the following metadata with every trace:

-   **Session ID**: The `thread_id` of the conversation is automatically used as the `langfuse_session_id`. This groups all runs from the same thread under a single session in Langfuse.
-   **User ID**: The `user.identity` is used as the `langfuse_user_id`, allowing you to filter traces by user.
-   **Tags**: A set of default tags are automatically added to each trace to provide context:
    -   `aegra_run`: Identifies the trace as originating from an Aegra server.
    -   `run:<run_id>`: The specific ID of the run.
    -   `thread:<thread_id>`: The thread ID.
    -   `user:<user_id>`: The user ID.

This metadata-rich tracing allows you to easily debug issues, analyze performance, and understand how your agents are being used, all from the Langfuse UI.
-   **IMPORTANT**: When you make changes in .env restart the server.

## Future Enhancements

-   **Trace ID Correlation**: To make debugging even easier, we plan to set the Langfuse `trace_id` to be the same as the Aegra `run_id`. This will allow for a direct one-to-one mapping between a run in our system and its corresponding trace in Langfuse.

For more detailed information about Langfuse and its features, please refer to the [official Langfuse documentation](https://langfuse.com/docs).
