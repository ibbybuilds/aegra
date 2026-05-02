"""In-process registry of run-cancellation reasons.

``execute_run`` can receive CancelledError from three sources: user
cancel, lease loss, or timeout. They are disambiguated by recording
which reason the run_id was tagged with before ``task.cancel()``.

Lives in ``core/`` (no service dependencies) so any layer — API
routes, broker managers, executors — can use it without circular
imports. Same shape as ``core/active_runs.py``.

THREADING / LOOP MODEL: this registry assumes a single asyncio event
loop per process. Do not invoke from threads, signal handlers, or
``atexit`` callbacks — the underlying dict is not lock-protected.
Cross-instance cancellation is handled by ``RedisBrokerManager``,
which receives pubsub messages on the same loop.

Precedence rule: a run is tagged with at most one reason. ``lease_loss``
always wins — once set it is never downgraded to ``"user"`` (only an
explicit ``clear`` removes it). ``execute_run`` reads the tag in this
order and acts on the first hit: ``lease_loss`` > ``user`` > timeout
(default). The precedence is enforced inside ``mark`` so an in-flight
user cancel arriving after a heartbeat-driven lease loss cannot make the
old worker finalize the run as ``interrupted`` and clobber the rerun.
"""

from typing import Literal

CancellationReason = Literal["user", "lease_loss"]


class CancellationRegistry:
    """Per-process registry tagging in-flight runs with a cancel reason."""

    def __init__(self) -> None:
        self._tags: dict[str, CancellationReason] = {}

    def mark(self, run_id: str, reason: CancellationReason) -> None:
        """Tag a run with a cancel reason.

        ``lease_loss`` always wins: a later ``mark(..., "user")`` is
        ignored if a lease-loss tag is already present. Without this
        precedence, a user cancel arriving in the overlap window between
        heartbeat-driven lease loss and the rerun would erase the
        lease-loss tag, and ``execute_run`` on the old worker would
        finalize the run as ``interrupted`` — clobbering the rerun's
        eventual outcome.
        """
        if self._tags.get(run_id) == "lease_loss" and reason != "lease_loss":
            return
        self._tags[run_id] = reason

    def reason_of(self, run_id: str) -> CancellationReason | None:
        """Return the tagged reason or ``None`` if the run has no tag."""
        return self._tags.get(run_id)

    def clear(self, run_id: str, *, only: CancellationReason | None = None) -> None:
        """Drop the tag for ``run_id``.

        ``only`` restricts removal to a specific reason — used to roll
        back a ``mark(..., "user")`` without disturbing a lease-loss tag
        that arrived in the meantime. Default removes any tag.
        """
        if only is None or self._tags.get(run_id) == only:
            self._tags.pop(run_id, None)

    def clear_all(self) -> None:
        """Drop every tag. Test-only — production code uses ``clear(run_id)``."""
        self._tags.clear()


cancellations = CancellationRegistry()
