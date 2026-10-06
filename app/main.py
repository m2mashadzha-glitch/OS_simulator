from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.simulator.engine import SimulationEngine

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
PAGES = {
    "home": "index.html",
    "cpu": "cpu.html",
    "memory": "memory.html",
    "virtual": "virtual.html",
    "raid": "raid.html",
    "metrics": "metrics.html",
}

app = FastAPI(
    title="Operating System Resource Simulator",
    description="SCSB082 Advanced OS – process, memory, VM and RAID simulator",
    version="1.1.0",
)

engine = SimulationEngine()


class ConfigureRequest(BaseModel):
    algorithm: Optional[str] = None
    quantum: Optional[int] = Field(default=None, ge=1)
    ram_size_kb: Optional[int] = Field(default=None, ge=4)
    page_size_kb: Optional[int] = Field(default=None, ge=1)
    virtual_size_kb: Optional[int] = Field(default=None, ge=4)
    replacement: Optional[str] = None
    raid_level: Optional[str] = None
    num_disks: Optional[int] = Field(default=None, ge=2)


class RunRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=500)


class DiskRequest(BaseModel):
    disk_id: int = Field(default=2, ge=1)


class RefsRequest(BaseModel):
    refs: List[int] = Field(default_factory=list)


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / PAGES[name])


@app.get("/")
def home() -> FileResponse:
    return _page("home")


@app.get("/cpu")
def cpu_page() -> FileResponse:
    return _page("cpu")


@app.get("/memory")
def memory_page() -> FileResponse:
    return _page("memory")


@app.get("/virtual")
def virtual_page() -> FileResponse:
    return _page("virtual")


@app.get("/raid")
def raid_page() -> FileResponse:
    return _page("raid")


@app.get("/metrics")
def metrics_page() -> FileResponse:
    return _page("metrics")


@app.get("/api/state")
def get_state() -> dict:
    return engine.state()


@app.post("/api/reset")
def reset() -> dict:
    engine.reset()
    return engine.state()


@app.post("/api/step")
def step() -> dict:
    return engine.step()


@app.post("/api/run")
def run(body: RunRequest) -> dict:
    return engine.run_for(body.steps)


@app.post("/api/generate-processes")
def generate_processes() -> dict:
    engine.generate_processes()
    return engine.state()


@app.post("/api/demo")
def load_demo() -> dict:
    engine.load_demo_scenario()
    return engine.state()


@app.post("/api/configure")
def configure(body: ConfigureRequest) -> dict:
    engine.configure(**body.model_dump(exclude_none=True))
    return engine.state()


@app.post("/api/fail-disk")
def fail_disk(body: DiskRequest) -> dict:
    return engine.fail_disk(body.disk_id)


@app.post("/api/recover-disk")
def recover_disk(body: DiskRequest) -> dict:
    return engine.recover_disk(body.disk_id)


@app.post("/api/page-refs")
def page_refs(body: RefsRequest) -> dict:
    if not body.refs:
        raise HTTPException(status_code=400, detail="refs required")
    engine.generate_page_references(body.refs)
    return engine.state()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
