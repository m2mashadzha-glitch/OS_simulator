"""CPU scheduling policies for the research-centre HPC node."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from .ready_queue import ReadyQueue
from .research_process import ResearchProcess


class SchedulingPolicy(str, Enum):
    FCFS = "FCFS"
    ROUND_ROBIN = "Round Robin"
    SJF = "Shortest Job First"
    PRIORITY = "Priority"


class CpuScheduler(ABC):
    policy: SchedulingPolicy
    uses_time_quantum: bool = False

    @abstractmethod
    def select(self, ready_queue: ReadyQueue) -> ResearchProcess | None:
        raise NotImplementedError


class FcfsScheduler(CpuScheduler):
    policy = SchedulingPolicy.FCFS

    def select(self, ready_queue: ReadyQueue) -> ResearchProcess | None:
        return ready_queue.dequeue()


class RoundRobinScheduler(CpuScheduler):
    policy = SchedulingPolicy.ROUND_ROBIN
    uses_time_quantum = True

    def __init__(self, time_quantum: int = 4) -> None:
        if time_quantum < 1:
            raise ValueError("time_quantum must be at least 1")
        self.time_quantum = time_quantum

    def select(self, ready_queue: ReadyQueue) -> ResearchProcess | None:
        return ready_queue.dequeue()


class ShortestJobFirstScheduler(CpuScheduler):
    policy = SchedulingPolicy.SJF

    def select(self, ready_queue: ReadyQueue) -> ResearchProcess | None:
        if len(ready_queue) == 0:
            return None
        chosen = min(ready_queue, key=lambda process: process.remaining_burst or 0)
        ready_queue.remove(chosen)
        return chosen


class PriorityScheduler(CpuScheduler):
    policy = SchedulingPolicy.PRIORITY

    def select(self, ready_queue: ReadyQueue) -> ResearchProcess | None:
        if len(ready_queue) == 0:
            return None
        chosen = min(
            ready_queue,
            key=lambda process: (process.priority, process.arrival_time),
        )
        ready_queue.remove(chosen)
        return chosen


def build_scheduler(
    policy: SchedulingPolicy | str,
    time_quantum: int = 4,
) -> CpuScheduler:
    if isinstance(policy, str):
        normalised = policy.strip().lower().replace("_", " ").replace("-", " ")
        mapping = {
            "fcfs": SchedulingPolicy.FCFS,
            "first come first served": SchedulingPolicy.FCFS,
            "round robin": SchedulingPolicy.ROUND_ROBIN,
            "rr": SchedulingPolicy.ROUND_ROBIN,
            "sjf": SchedulingPolicy.SJF,
            "shortest job first": SchedulingPolicy.SJF,
            "priority": SchedulingPolicy.PRIORITY,
        }
        if normalised not in mapping:
            raise ValueError(f"Unknown scheduling policy: {policy}")
        policy = mapping[normalised]

    if policy is SchedulingPolicy.FCFS:
        return FcfsScheduler()
    if policy is SchedulingPolicy.ROUND_ROBIN:
        return RoundRobinScheduler(time_quantum=time_quantum)
    if policy is SchedulingPolicy.SJF:
        return ShortestJobFirstScheduler()
    if policy is SchedulingPolicy.PRIORITY:
        return PriorityScheduler()
    raise ValueError(f"Unsupported scheduling policy: {policy}")
