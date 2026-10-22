"""
SCSB082 required experiments (§16) using the research-centre simulator.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.simulator.cpu_scheduler import SchedulingPolicy
from app.simulator.hpc_simulator import DEFAULT_PAGE_REFERENCES
from app.simulator.page_replacement import compare_algorithms
from app.simulator.process_execution import ProcessExecutionEngine
from app.simulator.raid_storage import RAID_SPECS, RaidArray
from app.simulator.workloads import research_centre_baseline_workload

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)


def experiment_cpu() -> dict:
    workload = research_centre_baseline_workload()
    rows = []
    for policy in (SchedulingPolicy.FCFS, SchedulingPolicy.ROUND_ROBIN):
        engine = ProcessExecutionEngine(scheduling_policy=policy, time_quantum=4)
        engine.load_workload(workload)
        snap = engine.run_to_completion()
        rows.append({"policy": policy.value, **snap["metrics"], "time": snap["current_time"]})
    return {"experiment": "CPU Scheduling", "results": rows}


def experiment_memory_size() -> dict:
    from app.simulator.memory_manager import MemoryManager

    refs = DEFAULT_PAGE_REFERENCES
    rows = []
    for frames in (8, 16, 32):
        memory = MemoryManager(ram_size_kb=frames * 4, page_size_kb=4)
        memory.register_process("P1", size_kb=48)
        for index, page in enumerate(refs):
            future = [("P1", ref) for ref in refs[index + 1 :]]
            memory.access_page(
                "P1",
                page % 12,
                replacement_algo="FIFO",
                future_refs=future,
            )
        rows.append({"frames": frames, **memory.metrics()})
    return {"experiment": "Memory Size", "results": rows}


def experiment_replacement() -> dict:
    return {
        "experiment": "Page Replacement",
        **compare_algorithms(DEFAULT_PAGE_REFERENCES, frame_count=4),
    }


def experiment_virtual() -> dict:
    return {
        "experiment": "Virtual Memory",
        "physical_memory_kb": 16,
        "virtual_memory_kb": 64,
        "page_size_kb": 4,
        "explanation": (
            "With 16 KB RAM and 4 KB pages only 4 frames are resident, but the "
            "64 KB virtual address space provides 16 virtual pages. Demand paging "
            "loads pages on reference so the 48 KB research process can execute."
        ),
    }


def experiment_raid() -> dict:
    rows = []
    for level in ("RAID 0", "RAID 1", "RAID 5", "RAID 6", "RAID 10"):
        disks = RAID_SPECS[level]["min_disks"]
        if level in {"RAID 5", "RAID 6", "RAID 10"}:
            disks = max(disks, 4)
        array = RaidArray(level=level, disk_count=disks)
        before = array.snapshot()
        array.fail_disk(2 if disks >= 2 else 1)
        after = array.snapshot()
        rows.append(
            {
                "level": level,
                "disks": disks,
                "comparison": before["comparison"],
                "after_fail_disk_2_available": after["data_available"],
                "event": after["last_event"],
            }
        )
    return {
        "experiment": "RAID",
        "results": rows,
        "recommendation": (
            "Prefer RAID 5 for the university research workload: strong read "
            "performance for large datasets, one-disk fault tolerance, and better "
            "capacity efficiency than RAID 1/10. Use RAID 6 if dual-disk failure "
            "protection is required."
        ),
    }


def main() -> None:
    report = {
        "module": "SCSB082",
        "experiments": [
            experiment_cpu(),
            experiment_memory_size(),
            experiment_replacement(),
            experiment_virtual(),
            experiment_raid(),
        ],
    }
    path = OUT / "experiment_results.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {path}")
    for block in report["experiments"]:
        print("-", block["experiment"])


if __name__ == "__main__":
    main()
