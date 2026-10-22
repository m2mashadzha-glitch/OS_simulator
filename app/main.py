"""
University Research Centre HPC Resource Simulator — SCSB082 complete build.
"""

from __future__ import annotations

from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.simulator.cpu_scheduler import SchedulingPolicy
    from app.simulator.hpc_simulator import DEFAULT_PAGE_REFERENCES, HpcResourceSimulator
else:
    from .simulator.cpu_scheduler import SchedulingPolicy
    from .simulator.hpc_simulator import DEFAULT_PAGE_REFERENCES, HpcResourceSimulator

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

app = FastAPI(
    title="Research Centre HPC Resource Simulator",
    description="SCSB082 complete OS resource-management simulator.",
    version="1.0.0",
)

sim = HpcResourceSimulator()


class SchedulerConfig(BaseModel):
    policy: str
    time_quantum: int = Field(default=4, ge=1)
    processor_count: int = Field(default=1, ge=1, le=8)


class ProcessInput(BaseModel):
    process_id: str = Field(min_length=1, max_length=20)
    arrival_time: int = Field(ge=0)
    burst_time: int = Field(ge=1)
    priority: int = Field(ge=1)
    process_size_kb: int = Field(ge=1)
    memory_requirement_kb: int | None = Field(default=None, ge=1)
    description: str = ""

    @field_validator("process_id")
    @classmethod
    def clean_id(cls, value: str) -> str:
        cleaned = value.strip().upper()
        digits = "".join(ch for ch in cleaned if ch.isdigit())
        if not digits:
            raise ValueError("process_id must include a number, e.g. P1")
        return f"P{digits}"


class CustomWorkloadRequest(BaseModel):
    name: str = "Custom Research Workload"
    scenario: str = "User-defined research jobs on the HPC node"
    processes: list[ProcessInput] = Field(min_length=1)


class MemoryConfig(BaseModel):
    ram_size_kb: int = Field(default=32, ge=4)
    page_size_kb: int = Field(default=4, ge=1)
    frame_size_kb: int = Field(default=4, ge=1)
    virtual_memory_kb: int = Field(default=64, ge=4)
    memory_scheme: str = Field(default="Paging")
    paging_mode: str = Field(default="Demand paging")
    frame_count: int | None = Field(default=None, ge=1)


class ReplacementConfig(BaseModel):
    algorithm: str = "FIFO"


class ReferenceConfig(BaseModel):
    references: list[int] = Field(min_length=1)


class RaidConfig(BaseModel):
    level: str = "RAID 5"
    disk_count: int = Field(default=4, ge=2)


class FailDiskRequest(BaseModel):
    disk_id: int = Field(ge=1)


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC / name)


@app.get("/")
def home() -> FileResponse:
    return _page("index.html")


@app.get("/cpu")
def cpu_page() -> FileResponse:
    return _page("cpu.html")


@app.get("/memory")
def memory_page() -> FileResponse:
    return _page("memory.html")


@app.get("/virtual")
def virtual_page() -> FileResponse:
    return _page("virtual.html")


@app.get("/raid")
def raid_page() -> FileResponse:
    return _page("raid.html")


@app.get("/metrics")
def metrics_page() -> FileResponse:
    return _page("metrics.html")


@app.get("/api/state")
def get_state() -> dict:
    return sim.snapshot()


@app.post("/api/reset")
def reset() -> dict:
    sim.reset()
    return sim.snapshot()


@app.post("/api/reset-defaults")
def reset_defaults() -> dict:
    """Clear workload and restore default memory / RAID / scheduler settings."""
    sim.reset_to_defaults()
    return sim.snapshot()


@app.post("/api/start")
def start() -> dict:
    sim.cpu.start()
    return sim.snapshot()


@app.post("/api/pause")
def pause() -> dict:
    sim.cpu.pause()
    return sim.snapshot()


@app.post("/api/step")
def step() -> dict:
    return sim.step()


@app.post("/api/run")
def run_simulation() -> dict:
    # Run CPU to completion while consuming page refs when possible.
    guard = 0
    while not sim.cpu.is_complete and guard < 10000:
        sim.step()
        guard += 1
    sim._record_scheme_stats()
    if sim.cpu.is_complete and sim.last_run is None:
        sim._save_last_run()
    return sim.snapshot()


@app.post("/api/run-trace")
def run_trace() -> dict:
    return sim.run_page_trace()


@app.post("/api/scheduler")
def configure_scheduler(config: SchedulerConfig) -> dict:
    try:
        sim.cpu.set_scheduling_policy(
            config.policy,
            time_quantum=config.time_quantum,
            processor_count=config.processor_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return sim.snapshot()


@app.post("/api/workload/custom")
def load_custom_workload(request: CustomWorkloadRequest) -> dict:
    ids = [item.process_id for item in request.processes]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Each process_id must be unique.")
    process_dicts = []
    for item in request.processes:
        size = item.process_size_kb
        memory = item.memory_requirement_kb if item.memory_requirement_kb is not None else size
        process_dicts.append(
            {
                "process_id": item.process_id,
                "arrival_time": item.arrival_time,
                "burst_time": item.burst_time,
                "priority": item.priority,
                "process_size_kb": size,
                "memory_requirement_kb": memory,
                "description": item.description,
            }
        )
    sim.load_process_dicts(
        process_dicts,
        name=request.name.strip() or "Custom Research Workload",
        scenario=request.scenario.strip() or "User-defined research jobs on the HPC node",
    )
    return sim.snapshot()


@app.post("/api/memory/config")
def memory_config(config: MemoryConfig) -> dict:
    page_size = config.page_size_kb
    frame_size = config.frame_size_kb
    # RAM = frame_count × frame_size when frames are set explicitly
    if config.frame_count is not None:
        ram_size = max(frame_size, config.frame_count * frame_size)
    else:
        ram_size = config.ram_size_kb
    if config.virtual_memory_kb < ram_size:
        raise HTTPException(
            status_code=400,
            detail="Virtual memory should be >= physical RAM.",
        )
    try:
        sim.configure_memory(
            ram_size,
            page_size,
            config.virtual_memory_kb,
            memory_scheme=config.memory_scheme,
            frame_size_kb=frame_size,
            frame_count=config.frame_count,
            paging_mode=config.paging_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return sim.snapshot()


@app.post("/api/memory/scheme")
def memory_scheme(config: MemoryConfig) -> dict:
    """Switch paging/segmentation while keeping current size settings."""
    try:
        sim.set_memory_scheme(config.memory_scheme)
        sim.configure_memory(
            config.ram_size_kb,
            config.page_size_kb,
            config.virtual_memory_kb,
            memory_scheme=config.memory_scheme,
            frame_size_kb=config.frame_size_kb,
            frame_count=config.frame_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return sim.snapshot()


@app.post("/api/memory/replacement")
def memory_replacement(config: ReplacementConfig) -> dict:
    sim.set_replacement_algorithm(config.algorithm)
    return sim.snapshot()


@app.post("/api/memory/references")
def memory_references(config: ReferenceConfig) -> dict:
    sim.set_page_references(config.references)
    return sim.snapshot()


@app.get("/api/memory/compare-replacement")
def compare_replacement() -> dict:
    return sim.compare_replacement()


@app.post("/api/raid/config")
def raid_config(config: RaidConfig) -> dict:
    try:
        sim.configure_raid(config.level, config.disk_count)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return sim.snapshot()


@app.post("/api/raid/fail")
def raid_fail(request: FailDiskRequest) -> dict:
    try:
        sim.raid.fail_disk(request.disk_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sim._log(sim.raid.last_event, "raid")
    return sim.snapshot()


@app.post("/api/raid/recover")
def raid_recover() -> dict:
    sim.raid.recover()
    sim._log(sim.raid.last_event, "raid")
    return sim.snapshot()


@app.get("/api/policies")
def list_policies() -> dict:
    return {
        "policies": [policy.value for policy in SchedulingPolicy],
        "default": SchedulingPolicy.FCFS.value,
        "default_references": DEFAULT_PAGE_REFERENCES,
    }


app.mount("/static", StaticFiles(directory=STATIC), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
