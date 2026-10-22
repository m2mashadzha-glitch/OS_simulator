"""Gantt chart recording for CPU execution on the HPC node."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GanttSlice:
    start_time: int
    end_time: int
    process_id: str | None
    label: str
    cpu_id: int = 0

    @property
    def duration(self) -> int:
        return self.end_time - self.start_time

    def to_dict(self) -> dict:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "process_id": self.process_id,
            "label": self.label,
            "cpu_id": self.cpu_id,
        }


@dataclass
class GanttChart:
    slices: list[GanttSlice] = field(default_factory=list)
    # Per-CPU open slice: cpu_id -> (start_time, process_id)
    _open: dict[int, tuple[int, str | None]] = field(default_factory=dict, repr=False)

    def clear(self) -> None:
        self.slices.clear()
        self._open.clear()

    def note_activity(
        self,
        current_time: int,
        process_id: str | None,
        cpu_id: int = 0,
    ) -> None:
        open_state = self._open.get(cpu_id)
        if open_state is not None:
            start, open_pid = open_state
            if open_pid == process_id:
                return
            if current_time > start:
                self._close_slice(cpu_id, current_time)
        self._open[cpu_id] = (current_time, process_id)

    def finish(self, current_time: int) -> None:
        for cpu_id in list(self._open.keys()):
            start, _ = self._open[cpu_id]
            if current_time > start:
                self._close_slice(cpu_id, current_time)
        self._open.clear()

    def _close_slice(self, cpu_id: int, end_time: int) -> None:
        start, process_id = self._open.pop(cpu_id)
        if process_id is None:
            label = f"CPU{cpu_id + 1}:IDLE"
        else:
            label = f"CPU{cpu_id + 1}:{process_id}"
        self.slices.append(
            GanttSlice(
                start_time=start,
                end_time=end_time,
                process_id=process_id,
                label=label,
                cpu_id=cpu_id,
            )
        )

    def to_list(self, current_time: int | None = None) -> list[dict]:
        """Return closed slices, plus open in-progress bars when current_time is set."""
        out = [slice_.to_dict() for slice_ in self.slices]
        if current_time is None:
            return out
        for cpu_id in sorted(self._open):
            start, process_id = self._open[cpu_id]
            end = current_time if current_time > start else start + 1
            if process_id is None:
                label = f"CPU{cpu_id + 1}:IDLE"
            else:
                label = f"CPU{cpu_id + 1}:{process_id}"
            out.append(
                GanttSlice(
                    start_time=start,
                    end_time=end,
                    process_id=process_id,
                    label=label,
                    cpu_id=cpu_id,
                ).to_dict()
            )
        return out
