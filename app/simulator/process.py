from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


STATUSES = ("New", "Ready", "Running", "Waiting", "Terminated")


@dataclass
class Process:
    pid: str
    arrival: int
    burst: int
    priority: int
    size_kb: int
    page_size_kb: int = 4
    remaining: Optional[int] = None
    status: str = "New"
    start_time: Optional[int] = None
    finish_time: Optional[int] = None
    first_response_time: Optional[int] = None
    waiting_time: int = 0
    page_refs: List[int] = field(default_factory=list)
    ref_index: int = 0
    quantum_used: int = 0

    def __post_init__(self) -> None:
        if self.remaining is None:
            self.remaining = self.burst

    @property
    def num_pages(self) -> int:
        return max(1, (self.size_kb + self.page_size_kb - 1) // self.page_size_kb)

    @property
    def turnaround_time(self) -> Optional[int]:
        if self.finish_time is None:
            return None
        return self.finish_time - self.arrival

    @property
    def response_time(self) -> Optional[int]:
        if self.first_response_time is None:
            return None
        return self.first_response_time - self.arrival

    def next_page_ref(self) -> Optional[int]:
        if not self.page_refs:
            # Default walk through pages while running.
            if self.num_pages <= 0:
                return None
            page = self.ref_index % self.num_pages
            self.ref_index += 1
            return page
        if self.ref_index >= len(self.page_refs):
            return self.page_refs[-1]
        page = self.page_refs[self.ref_index]
        self.ref_index += 1
        return page

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "arrival": self.arrival,
            "burst": self.burst,
            "remaining": self.remaining,
            "priority": self.priority,
            "size_kb": self.size_kb,
            "num_pages": self.num_pages,
            "status": self.status,
            "waiting_time": self.waiting_time,
            "turnaround_time": self.turnaround_time,
            "response_time": self.response_time,
            "start_time": self.start_time,
            "finish_time": self.finish_time,
            "ref_index": self.ref_index,
        }
