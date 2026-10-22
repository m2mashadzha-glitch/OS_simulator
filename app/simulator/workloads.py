"""Named research-centre workloads used by the simulator and experiments."""

from __future__ import annotations

import json
from pathlib import Path

from .research_process import ResearchProcess, ResearchWorkload

ROOT = Path(__file__).resolve().parents[2]
TEST_DATA = ROOT / "test_data"


def load_workload_file(path: Path | str) -> ResearchWorkload:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    page_size = int(data.get("page_size_kb", 4))
    processes = [
        ResearchProcess(
            process_id=item["process_id"],
            arrival_time=int(item["arrival_time"]),
            burst_time=int(item["burst_time"]),
            priority=int(item["priority"]),
            memory_requirement_kb=int(
                item.get("memory_requirement_kb", item["process_size_kb"])
            ),
            process_size_kb=int(item["process_size_kb"]),
            page_size_kb=page_size,
            description=str(item.get("description", "")),
        )
        for item in data["processes"]
    ]
    return ResearchWorkload(
        name=data.get("name", Path(path).name),
        scenario=data.get("scenario", ""),
        processes=processes,
    )


def research_centre_baseline_workload() -> ResearchWorkload:
    return load_workload_file(TEST_DATA / "research_centre_baseline_workload.json")
