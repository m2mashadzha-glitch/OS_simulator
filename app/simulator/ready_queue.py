"""Ready queue for research processes waiting on the HPC CPU."""

from __future__ import annotations

from collections import deque

from .research_process import ResearchProcess


class ReadyQueue:
    def __init__(self) -> None:
        self._queue: deque[ResearchProcess] = deque()

    def __len__(self) -> int:
        return len(self._queue)

    def __iter__(self):
        return iter(self._queue)

    def clear(self) -> None:
        self._queue.clear()

    def enqueue(self, process: ResearchProcess) -> None:
        self._queue.append(process)

    def dequeue(self) -> ResearchProcess | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def peek(self) -> ResearchProcess | None:
        if not self._queue:
            return None
        return self._queue[0]

    def remove(self, process: ResearchProcess) -> None:
        self._queue = deque(item for item in self._queue if item is not process)

    def process_ids(self) -> list[str]:
        return [process.process_id for process in self._queue]

    def to_list(self) -> list[dict]:
        return [process.to_dict() for process in self._queue]
