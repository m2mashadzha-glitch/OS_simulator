"""Stores completed CPU simulation runs for comparison charts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[2]
HISTORY_PATH = ROOT / "data" / "run_history.json"
MAX_RUNS = 20


@dataclass
class RunRecord:
    run_id: int
    recorded_at: str
    workload_name: str
    scheduling_policy: str
    time_quantum: int | None
    total_execution_time: int
    cpu_utilisation: float
    average_waiting_time: float
    average_turnaround_time: float
    average_response_time: float
    process_count: int
    completed_count: int
    per_process: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class RunHistory:
    def __init__(self, path: Path = HISTORY_PATH) -> None:
        self.path = path
        self._lock = Lock()
        self._runs: list[RunRecord] = []
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._runs = [RunRecord(**item) for item in raw.get("runs", [])]
        self._next_id = int(raw.get("next_id", len(self._runs) + 1))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "next_id": self._next_id,
            "runs": [run.to_dict() for run in self._runs],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add_from_snapshot(self, snapshot: dict) -> RunRecord:
        metrics = snapshot["metrics"]
        per_process = [
            {
                "process_id": process["process_id"],
                "description": process.get("description", ""),
                "burst_time": process["burst_time"],
                "waiting_time": process["waiting_time"],
                "turnaround_time": process["turnaround_time"],
                "response_time": process.get("response_time"),
            }
            for process in snapshot.get("processes", [])
            if process.get("status") == "Terminated"
        ]
        record = RunRecord(
            run_id=self._next_id,
            recorded_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            workload_name=snapshot.get("workload_name", "Workload"),
            scheduling_policy=snapshot.get("scheduling_policy", "Unknown"),
            time_quantum=snapshot.get("time_quantum"),
            total_execution_time=int(snapshot.get("current_time", 0)),
            cpu_utilisation=float(metrics.get("cpu_utilisation", 0)),
            average_waiting_time=float(metrics.get("average_waiting_time", 0)),
            average_turnaround_time=float(metrics.get("average_turnaround_time", 0)),
            average_response_time=float(metrics.get("average_response_time", 0)),
            process_count=int(metrics.get("total_processes", 0)),
            completed_count=int(metrics.get("completed_count", 0)),
            per_process=per_process,
        )
        with self._lock:
            self._next_id += 1
            self._runs.append(record)
            self._runs = self._runs[-MAX_RUNS:]
            self._save()
        return record

    def list_runs(self) -> list[dict]:
        with self._lock:
            return [run.to_dict() for run in self._runs]

    def clear(self) -> None:
        with self._lock:
            self._runs = []
            self._save()


run_history = RunHistory()
