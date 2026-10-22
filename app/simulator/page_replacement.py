"""
Virtual-memory page-replacement algorithms (FIFO, LRU, Optimal).

Aligned with classic textbook treatments (e.g. Stallings): when a referenced
page is not resident and no free frame exists, the OS selects a victim page.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class ReplacementStep:
    reference: int
    frames: list[int | None]
    fault: bool

    def to_dict(self) -> dict:
        return {
            "reference": self.reference,
            "frames": self.frames,
            "fault": self.fault,
        }


@dataclass
class ReplacementResult:
    algorithm: str
    frame_count: int
    references: list[int]
    steps: list[ReplacementStep] = field(default_factory=list)
    page_faults: int = 0
    page_hits: int = 0

    @property
    def fault_rate(self) -> float:
        total = len(self.references)
        return round((self.page_faults / total) * 100, 2) if total else 0.0

    @property
    def hit_rate(self) -> float:
        total = len(self.references)
        return round((self.page_hits / total) * 100, 2) if total else 0.0

    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "frame_count": self.frame_count,
            "page_references": len(self.references),
            "page_faults": self.page_faults,
            "page_hits": self.page_hits,
            "fault_rate": self.fault_rate,
            "hit_rate": self.hit_rate,
            "steps": [step.to_dict() for step in self.steps],
        }


def run_fifo(references: list[int], frame_count: int) -> ReplacementResult:
    frames: list[int | None] = [None] * frame_count
    order: deque[int] = deque()
    result = ReplacementResult("FIFO", frame_count, list(references))
    for ref in references:
        if ref in frames:
            result.page_hits += 1
            result.steps.append(ReplacementStep(ref, list(frames), False))
            continue
        result.page_faults += 1
        if None in frames:
            idx = frames.index(None)
            frames[idx] = ref
            order.append(ref)
        else:
            victim = order.popleft()
            idx = frames.index(victim)
            frames[idx] = ref
            order.append(ref)
        result.steps.append(ReplacementStep(ref, list(frames), True))
    return result


def run_lru(references: list[int], frame_count: int) -> ReplacementResult:
    frames: list[int | None] = [None] * frame_count
    last_used: dict[int, int] = {}
    result = ReplacementResult("LRU", frame_count, list(references))
    for time, ref in enumerate(references):
        if ref in frames:
            result.page_hits += 1
            last_used[ref] = time
            result.steps.append(ReplacementStep(ref, list(frames), False))
            continue
        result.page_faults += 1
        if None in frames:
            idx = frames.index(None)
            frames[idx] = ref
        else:
            victim = min(
                (page for page in frames if page is not None),
                key=lambda page: last_used.get(page, -1),
            )
            idx = frames.index(victim)
            frames[idx] = ref
            last_used.pop(victim, None)
        last_used[ref] = time
        result.steps.append(ReplacementStep(ref, list(frames), True))
    return result


def run_optimal(references: list[int], frame_count: int) -> ReplacementResult:
    frames: list[int | None] = [None] * frame_count
    result = ReplacementResult("Optimal", frame_count, list(references))
    for index, ref in enumerate(references):
        if ref in frames:
            result.page_hits += 1
            result.steps.append(ReplacementStep(ref, list(frames), False))
            continue
        result.page_faults += 1
        if None in frames:
            idx = frames.index(None)
            frames[idx] = ref
        else:
            def distance(page: int) -> int:
                try:
                    return references[index + 1 :].index(page)
                except ValueError:
                    return 10**9

            victim = max(
                (page for page in frames if page is not None),
                key=distance,
            )
            idx = frames.index(victim)
            frames[idx] = ref
        result.steps.append(ReplacementStep(ref, list(frames), True))
    return result


def compare_algorithms(
    references: list[int],
    frame_count: int,
) -> dict:
    results = [
        run_fifo(references, frame_count),
        run_lru(references, frame_count),
        run_optimal(references, frame_count),
    ]
    return {
        "references": references,
        "frame_count": frame_count,
        "results": [item.to_dict() for item in results],
    }
