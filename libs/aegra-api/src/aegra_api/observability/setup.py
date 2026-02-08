import logging

from aegra_api.observability.base import get_observability_manager
from aegra_api.observability.otel import otel_provider

logger = logging.getLogger(__name__)


def setup_observability() -> None:
    """
    Registers and initializes the observability subsystem.
    Handles global OpenTelemetry setup if enabled.
    """
    manager = get_observability_manager()

    # We are registering our single OTEL provider
    manager.register_provider(otel_provider)

    # Launching global instrumentation if the provider is active
    if otel_provider.is_enabled():
        try:
            otel_provider.setup()
            logger.info("Observability subsystem initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize observability: {e}")
    else:
        logger.info("Observability is disabled (no targets configured).")
