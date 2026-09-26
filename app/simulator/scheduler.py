from __future__ import annotations

from typing import List, Optional

from .process import Process


class Scheduler:
    """CPU scheduling policies used by the simulation engine."""

    ALGORITHMS = ("FCFS", "Round Robin", "SJF", "Priority")

    def __init__(self, algorithm: str = "FCFS", quantum: int = 4) -> None:
        self.algorithm = algorithm if algorithm in self.ALGORITHMS else "FCFS"
        self.quantum = max(1, quantum)

    def select(self, ready: List[Process]) -> Optional[Process]:
        if not ready:
            return None
        if self.algorithm == "FCFS":
            return min(ready, key=lambda p: (p.arrival, p.pid))
        if self.algorithm == "SJF":
            return min(ready, key=lambda p: (p.remaining or 0, p.arrival, p.pid))
        if self.algorithm == "Priority":
            # Lower number = higher priority
            return min(ready, key=lambda p: (p.priority, p.arrival, p.pid))
        # Round Robin: keep queue order (append on quantum expiry)
        return ready[0]

    def to_dict(self) -> dict:
        return {"algorithm": self.algorithm, "quantum": self.quantum}
