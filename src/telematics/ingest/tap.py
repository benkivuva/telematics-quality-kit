"""Fan out typed pipeline events through bounded, nonblocking subscriber queues."""

from queue import Empty, Full, Queue
from threading import Lock

from telematics.ingest.events import PipelineEvent


class EventSubscription:
    """One consumer's bounded event queue and drop counter."""

    def __init__(self, maxsize: int) -> None:
        self._queue: Queue[PipelineEvent] = Queue(maxsize=maxsize)
        self._lock = Lock()
        self._closed = False
        self._tap_dropped = 0

    @property
    def tap_dropped(self) -> int:
        """Number of this subscriber's oldest events discarded under backpressure."""
        with self._lock:
            return self._tap_dropped

    def get_nowait(self) -> PipelineEvent:
        """Return the next queued event without waiting."""
        with self._lock:
            return self._queue.get_nowait()

    def empty(self) -> bool:
        """Return whether this subscriber currently has no queued events."""
        with self._lock:
            return self._queue.empty()

    def _offer(self, event: PipelineEvent) -> bool:
        with self._lock:
            if self._closed:
                return False
            try:
                self._queue.put_nowait(event)
                return False
            except Full:
                pass
            try:
                self._queue.get_nowait()
            except Empty:
                pass
            else:
                self._tap_dropped += 1
            self._queue.put_nowait(event)
            return True

    def _close(self) -> None:
        with self._lock:
            self._closed = True
            while not self._queue.empty():
                self._queue.get_nowait()


class EventTap:
    """Publish events independently to subscribers without waiting for consumers."""

    def __init__(self) -> None:
        self._subscriptions: list[EventSubscription] = []
        self._lock = Lock()
        self._tap_dropped = 0

    @property
    def tap_dropped(self) -> int:
        """Cumulative event deliveries dropped across all subscribers."""
        with self._lock:
            return self._tap_dropped

    def subscribe(self, *, maxsize: int = 256) -> EventSubscription:
        """Create a subscriber with a strictly positive bounded queue."""
        if maxsize < 1:
            raise ValueError("subscriber queue size must be positive")
        subscription = EventSubscription(maxsize)
        with self._lock:
            self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        """Stop sending events to a subscriber and discard its queued events."""
        with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)
                subscription._close()

    def publish(self, event: PipelineEvent) -> None:
        """Offer an event to each consumer, dropping that consumer's oldest if full."""
        with self._lock:
            subscriptions = tuple(self._subscriptions)
        for subscription in subscriptions:
            dropped = subscription._offer(event)
            if dropped:
                with self._lock:
                    self._tap_dropped += 1
