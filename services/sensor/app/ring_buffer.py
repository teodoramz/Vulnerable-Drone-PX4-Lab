from __future__ import annotations

from collections import deque
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class RingBuffer(Generic[T]):
    """Bounded FIFO buffer; appending past `capacity` evicts the oldest item."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._items: deque[T] = deque(maxlen=capacity)

    def append(self, item: T) -> None:
        self._items.append(item)

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return len(self._items)

    def all(self) -> list[T]:
        """All buffered items, oldest first."""
        return list(self._items)

    def recent(self, limit: int, predicate: Callable[[T], bool] | None = None) -> list[T]:
        """Up to `limit` most recent items, oldest to newest, optionally filtered."""
        items = list(self._items)
        if predicate is not None:
            items = [i for i in items if predicate(i)]
        if limit <= 0:
            return []
        return items[-limit:]
