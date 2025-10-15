import logging
import os

logger = logging.getLogger(__name__)

_LANGFUSE_LOGGING_ENABLED = os.getenv("LANGFUSE_LOGGING", "false").lower() == "true"


def get_tracing_callbacks() -> list:
    """
    Initializes and returns a list of tracing callbacks if enabled.
    """
    callbacks = []
    if _LANGFUSE_LOGGING_ENABLED:
        try:
            from langfuse.langchain import CallbackHandler

            # Handler is now stateless, metadata will be passed in config
            handler = CallbackHandler()
            callbacks.append(handler)
            logger.info("Langfuse tracing enabled, handler created.")
        except ImportError:
            logger.warning(
                "LANGFUSE_LOGGING is true, but 'langfuse' is not installed. "
                "Please run 'pip install langfuse' to enable tracing."
            )
        except Exception as e:
            logger.error(f"Failed to initialize Langfuse CallbackHandler: {e}")

    return callbacks
