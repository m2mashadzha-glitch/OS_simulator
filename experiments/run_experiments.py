"""Run the five required experiments and write CSV/PNG summaries."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.simulator.engine import DEMO_PAGE_REFS, SimulationEngine
from app.simulator.memory import MemoryManager

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)


def run_scheduler(algorithm: str) -> dict:
    eng = SimulationEngine()
    eng.configure(algorithm=algorithm, quantum=4)
    eng.generate_processes()
    for _ in range(200):
        if all(p.status == "Terminated" for p in eng.processes):
            break
        eng.step()
    m = eng.metrics()
    m["algorithm"] = algorithm
    return m


def run_memory_size(frames_kb: int) -> dict:
    mm = MemoryManager(ram_size_kb=frames_kb, page_size_kb=4, virtual_size_kb=64, replacement="LRU")
    mm.future_refs = list(DEMO_PAGE_REFS)
    mm.ensure_process("P", 12)
    for r in DEMO_PAGE_REFS:
        mm.access("P", r, mm.future_index)
    return {
        "ram_kb": frames_kb,
        "frames": mm.num_frames,
        "faults": mm.page_faults,
        "hits": mm.page_hits,
        "fault_rate": round(mm.fault_rate(), 2),
    }


def run_replacement() -> list:
    eng = SimulationEngine()
    eng.configure(ram_size_kb=16, page_size_kb=4, virtual_size_kb=64)
    return eng.compare_replacement(DEMO_PAGE_REFS)


def main() -> None:
    # Experiment 1 – CPU scheduling
    sched = [run_scheduler(a) for a in ("FCFS", "Round Robin", "SJF", "Priority")]
    with (OUT / "experiment1_scheduling.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sched[0].keys()))
        w.writeheader()
        w.writerows(sched)

    plt.figure(figsize=(8, 4))
    plt.bar([r["algorithm"] for r in sched], [r["average_waiting_time"] for r in sched], color="#0f6e6e")
    plt.title("Experiment 1 – Average Waiting Time")
    plt.ylabel("Time units")
    plt.tight_layout()
    plt.savefig(OUT / "experiment1_waiting.png")
    plt.close()

    # Experiment 2 – memory size
    mem = [run_memory_size(kb) for kb in (8, 16, 32)]
    with (OUT / "experiment2_memory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(mem[0].keys()))
        w.writeheader()
        w.writerows(mem)

    plt.figure(figsize=(8, 4))
    plt.plot([r["ram_kb"] for r in mem], [r["faults"] for r in mem], marker="o", color="#b86e00")
    plt.title("Experiment 2 – Page Faults vs RAM Size")
    plt.xlabel("RAM (KB)")
    plt.ylabel("Faults")
    plt.tight_layout()
    plt.savefig(OUT / "experiment2_faults.png")
    plt.close()

    # Experiment 3 – page replacement
    rep = run_replacement()
    with (OUT / "experiment3_replacement.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rep[0].keys()))
        w.writeheader()
        w.writerows(rep)

    plt.figure(figsize=(8, 4))
    plt.bar([r["algorithm"] for r in rep], [r["faults"] for r in rep], color="#1f7a45")
    plt.title("Experiment 3 – Page Faults by Replacement Algorithm")
    plt.ylabel("Faults")
    plt.tight_layout()
    plt.savefig(OUT / "experiment3_replacement.png")
    plt.close()

    # Experiment 4 – virtual memory note
    vm = {
        "physical_kb": 16,
        "virtual_kb": 64,
        "page_kb": 4,
        "physical_frames": 4,
        "virtual_pages": 16,
        "explanation": (
            "Virtual memory lets a 48KB process with 12 pages execute using only "
            "4 physical frames by swapping pages between RAM and secondary storage."
        ),
    }
    (OUT / "experiment4_virtual_memory.json").write_text(json.dumps(vm, indent=2), encoding="utf-8")

    # Experiment 5 – RAID comparison
    eng = SimulationEngine()
    raid_rows = eng.raid.comparison()
    with (OUT / "experiment5_raid.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(raid_rows[0].keys()))
        w.writeheader()
        w.writerows(raid_rows)
    recommendation = {
        "recommended": "RAID 5",
        "reason": (
            "For a university research centre, RAID 5 balances usable capacity and "
            "single-disk fault tolerance. RAID 6 is stronger (two-disk tolerance) "
            "but costs more capacity/write overhead; RAID 10 is fast and resilient "
            "per mirror pair but keeps only ~50% capacity. RAID 0 has no redundancy; "
            "RAID 1 wastes the most space on a multi-disk array."
        ),
    }
    (OUT / "experiment5_recommendation.json").write_text(
        json.dumps(recommendation, indent=2), encoding="utf-8"
    )

    summary = {
        "scheduling": sched,
        "memory_size": mem,
        "replacement": rep,
        "virtual_memory": vm,
        "raid": raid_rows,
        "raid_recommendation": recommendation,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote experiment outputs to {OUT}")


if __name__ == "__main__":
    main()
