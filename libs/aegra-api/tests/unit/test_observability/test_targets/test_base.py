"""Unit tests for the BaseOtelTarget abstract base class."""

import pytest
from opentelemetry.sdk.trace.export import SpanExporter

from aegra_api.observability.targets.base import BaseOtelTarget


class TestBaseOtelTarget:
    """Tests for the BaseOtelTarget interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that BaseOtelTarget cannot be instantiated directly."""
        with pytest.raises(TypeError) as excinfo:
            BaseOtelTarget()

        # Verify that the error relates to abstract methods
        assert "Can't instantiate abstract class" in str(excinfo.value)
        assert "name" in str(excinfo.value) or "get_exporter" in str(excinfo.value)

    def test_cannot_instantiate_incomplete_subclass(self):
        """Test that a subclass missing required methods cannot be instantiated."""

        class IncompleteTarget(BaseOtelTarget):
            @property
            def name(self) -> str:
                return "Incomplete"

            # get_exporter is missing

        with pytest.raises(TypeError) as excinfo:
            IncompleteTarget()

        assert "Can't instantiate abstract class" in str(excinfo.value)
        assert "get_exporter" in str(excinfo.value)

    def test_valid_subclass_works(self):
        """Test that a fully implemented subclass works correctly."""

        class ValidTarget(BaseOtelTarget):
            @property
            def name(self) -> str:
                return "ValidTarget"

            def get_exporter(self) -> SpanExporter | None:
                return None

        target = ValidTarget()
        assert isinstance(target, BaseOtelTarget)
        assert target.name == "ValidTarget"
        assert target.get_exporter() is None
