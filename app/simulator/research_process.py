"""Research jobs submitted to the university HPC environment."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil


class ProcessState(str, Enum):
    NEW = "New"
    READY = "Ready"
    RUNNING = "Running"
    WAITING = "Waiting/Blocked"
    TERMINATED = "Terminated"


@dataclass
class ResearchProcess:
    process_id: str
    arrival_time: int
    burst_time: int
    priority: int
    memory_requirement_kb: int
    process_size_kb: int
    page_size_kb: int = 4
    status: ProcessState = ProcessState.NEW
    remaining_burst: int | None = None
    start_time: int | None = None
    finish_time: int | None = None
    response_time: int | None = None
    waiting_time: int = 0
    turnaround_time: int = 0
    last_ready_time: int | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.remaining_burst is None:
            self.remaining_burst = self.burst_time
        if self.last_ready_time is None:
            self.last_ready_time = self.arrival_time

    @property
    def number_of_pages(self) -> int:
        return max(1, ceil(self.process_size_kb / self.page_size_kb))

    def mark_ready(self, current_time: int) -> None:
        self.status = ProcessState.READY
        self.last_ready_time = current_time

    def mark_running(self, current_time: int) -> None:
        if self.start_time is None:
            self.start_time = current_time
            self.response_time = current_time - self.arrival_time
        if self.last_ready_time is not None:
            self.waiting_time += current_time - self.last_ready_time
            self.last_ready_time = None
        self.status = ProcessState.RUNNING

    def mark_waiting(self, current_time: int) -> None:
        self.status = ProcessState.WAITING
        self.last_ready_time = current_time

    def mark_terminated(self, current_time: int) -> None:
        self.status = ProcessState.TERMINATED
        self.finish_time = current_time
        self.remaining_burst = 0
        self.turnaround_time = current_time - self.arrival_time

    def to_dict(self) -> dict:
        return {
            "process_id": self.process_id,
            "arrival_time": self.arrival_time,
            "burst_time": self.burst_time,
            "priority": self.priority,
            "memory_requirement_kb": self.memory_requirement_kb,
            "process_size_kb": self.process_size_kb,
            "number_of_pages": self.number_of_pages,
            "page_size_kb": self.page_size_kb,
            "status": self.status.value,
            "remaining_burst": self.remaining_burst,
            "start_time": self.start_time,
            "finish_time": self.finish_time,
            "response_time": self.response_time,
            "waiting_time": self.waiting_time,
            "turnaround_time": self.turnaround_time,
            "description": self.description,
        }


@dataclass
class ResearchWorkload:
    name: str
    scenario: str
    processes: list[ResearchProcess] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "scenario": self.scenario,
            "processes": [process.to_dict() for process in self.processes],
        }
