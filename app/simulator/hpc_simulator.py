"""
Integrated Research Centre HPC Resource Simulator.

Pipeline (assessment §12):
  PROCESS CREATED → READY QUEUE → CPU → MEMORY REQUEST → PAGE/SEGMENT TABLE
  → HIT/FAULT → SECONDARY/RAID STORAGE → MAIN MEMORY → EXECUTION → TERMINATION
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from .memory_manager import MemoryManager
from .page_replacement import compare_algorithms
from .process_execution import ProcessExecutionEngine
from .raid_storage import RaidArray
from .research_process import ResearchWorkload
from .segment_memory import SegmentMemoryManager


DEFAULT_PAGE_REFERENCES = [
    0, 1, 2, 3, 4, 5, 0, 1, 6, 7,
    2, 3, 8, 9, 0, 1, 4, 5, 10, 11,
]

MEMORY_SCHEMES = ("Paging", "Segmentation")
PAGING_MODES = ("Demand paging", "Prepaging")


@dataclass
class HpcResourceSimulator:
    """Coordinates process, memory, virtual-memory and RAID modules."""

    cpu: ProcessExecutionEngine = field(default_factory=ProcessExecutionEngine)
    memory: MemoryManager = field(
        default_factory=lambda: MemoryManager(ram_size_kb=32, page_size_kb=4)
    )
    segments: SegmentMemoryManager = field(
        default_factory=lambda: SegmentMemoryManager(ram_size_kb=32)
    )
    raid: RaidArray = field(default_factory=lambda: RaidArray(level="RAID 5", disk_count=4))
    memory_scheme: str = "Paging"
    paging_mode: str = "Demand paging"
    virtual_memory_kb: int = 64
    replacement_algorithm: str = "FIFO"
    page_reference_string: list[int] = field(
        default_factory=lambda: list(DEFAULT_PAGE_REFERENCES)
    )
    reference_index: int = 0
    kernel_log: list[dict] = field(default_factory=list)
    last_memory_event: dict | None = None
    scheme_run_stats: dict = field(default_factory=dict)
    peak_memory: dict = field(default_factory=dict)
    last_memory_map: dict | None = None
    last_run: dict | None = None
    _raid_finalized: bool = False

    def __post_init__(self) -> None:
        self.load_workload(
            ResearchWorkload(
                name="Custom Research Workload",
                scenario="User-defined research jobs on the HPC node",
                processes=[],
            )
        )

    def _log(self, message: str, kind: str = "info") -> None:
        self.kernel_log.append(
            {
                "time": self.cpu.current_time,
                "kind": kind,
                "message": message,
            }
        )
        self.kernel_log = self.kernel_log[-80:]

    def load_workload(self, workload: ResearchWorkload) -> None:
        self.cpu.page_size_kb = self.memory.page_size_kb
        self.cpu.load_workload(workload)
        self._sync_memory_tables()
        self._store_all_blocks_on_raid(replace=True)
        self._raid_finalized = False
        self.reference_index = 0
        self.last_memory_event = None
        self.peak_memory = {}
        self.last_memory_map = None
        self._log(f"Loaded workload: {workload.name}", "workload")

    def load_process_dicts(self, process_dicts: list[dict], name: str, scenario: str) -> None:
        self.cpu.workload_name = name
        self.cpu.scenario = scenario
        self.cpu.page_size_kb = self.memory.page_size_kb
        self.cpu.load_process_dicts(process_dicts)
        self._sync_memory_tables()
        self._store_all_blocks_on_raid(replace=True)
        self._raid_finalized = False
        self.reference_index = 0
        self.last_memory_event = None
        self.peak_memory = {}
        self.last_memory_map = None

    def _sync_memory_tables(self) -> None:
        self.memory.reconfigure(
            self.memory.ram_size_kb,
            self.memory.page_size_kb,
            self.memory.frame_size_kb,
        )
        self.segments.reconfigure(self.memory.ram_size_kb)
        for process in self.cpu.export_workload().processes:
            self.memory.register_process(process.process_id, process.process_size_kb)
            self.segments.register_process(process.process_id, process.process_size_kb)

    def _storage_labels_for_workload(self) -> list[str]:
        labels: list[str] = []
        for process in self.cpu.export_workload().processes:
            if self.memory_scheme == "Segmentation":
                table = self.segments.segment_tables.get(process.process_id, [])
                for entry in table:
                    labels.append(f"{process.process_id}:{entry.name}")
            else:
                page_count = self.memory.pages_required(process.process_size_kb)
                for page in range(page_count):
                    labels.append(f"{process.process_id}:pg{page}")
        return labels

    def _store_all_blocks_on_raid(self, *, replace: bool = False) -> None:
        labels = self._storage_labels_for_workload()
        if not labels:
            self.raid.clear_storage()
            return
        self.raid.store_blocks(labels, replace=replace)
        kind = "segment" if self.memory_scheme == "Segmentation" else "page"
        self._log(
            f"RAID {self.raid.level}: stored {len(labels)} {kind} block(s) "
            f"across {self.raid.disk_count} disks",
            "raid",
        )

    def set_memory_scheme(self, scheme: str) -> None:
        if scheme not in MEMORY_SCHEMES:
            raise ValueError(f"Unsupported memory scheme: {scheme}")
        self.memory_scheme = scheme
        self._sync_memory_tables()
        self._store_all_blocks_on_raid(replace=True)
        self.reference_index = 0
        self.last_memory_event = None
        self._raid_finalized = False
        self._log(f"Memory scheme = {scheme}", "config")

    def set_paging_mode(self, mode: str) -> None:
        if mode not in PAGING_MODES:
            raise ValueError(f"Unsupported paging mode: {mode}")
        self.paging_mode = mode
        self._log(f"Paging mode = {mode}", "config")

    def configure_memory(
        self,
        ram_size_kb: int,
        page_size_kb: int,
        virtual_memory_kb: int,
        memory_scheme: str | None = None,
        frame_size_kb: int | None = None,
        frame_count: int | None = None,
        paging_mode: str | None = None,
    ) -> None:
        if memory_scheme is not None:
            if memory_scheme not in MEMORY_SCHEMES:
                raise ValueError(f"Unsupported memory scheme: {memory_scheme}")
            self.memory_scheme = memory_scheme
        if paging_mode is not None:
            if paging_mode not in PAGING_MODES:
                raise ValueError(f"Unsupported paging mode: {paging_mode}")
            self.paging_mode = paging_mode
        self.virtual_memory_kb = virtual_memory_kb
        workload = self.cpu.export_workload()
        policy = self.cpu.scheduling_policy
        quantum = self.cpu.time_quantum
        processors = self.cpu.processor_count
        frame_sz = frame_size_kb if frame_size_kb is not None else page_size_kb
        self.memory.reconfigure(
            ram_size_kb,
            page_size_kb,
            frame_size_kb=frame_sz,
            frame_count=frame_count,
        )
        self.segments.reconfigure(self.memory.ram_size_kb)
        self.cpu.page_size_kb = page_size_kb
        self.cpu.load_workload(workload)
        self.cpu.set_scheduling_policy(
            policy, time_quantum=quantum, processor_count=processors
        )
        self._sync_memory_tables()
        self._store_all_blocks_on_raid(replace=True)
        self.reference_index = 0
        self.last_memory_event = None
        self.peak_memory = {}
        self.last_memory_map = None
        self._raid_finalized = False
        self._log(
            f"Memory reconfigured: scheme={self.memory_scheme} "
            f"paging={self.paging_mode} "
            f"RAM={self.memory.ram_size_kb}KB page={page_size_kb}KB "
            f"frame={self.memory.frame_size_kb}KB frames={self.memory.frame_count} "
            f"virtual={virtual_memory_kb}KB",
            "config",
        )

    def _prepage_process(self, process_id: str) -> None:
        """Load pages into RAM when a process enters Ready (prepaging)."""
        actions = self.memory.allocate_initial_pages(process_id)
        if not actions:
            self._log(
                f"Prepaging {process_id}: no free frames — pages stay on disk",
                "prepage",
            )
            return
        for action in actions:
            block = f"{process_id}:pg{action['page']}"
            self.raid.store_blocks([block])
        self.last_memory_event = {
            "result": "PREPAGE",
            "scheme": "Paging",
            "process_id": process_id,
            "page": actions[0]["page"],
            "frame": actions[0]["frame"],
            "relocation": self.memory.last_translation,
            "message": (
                f"Prepaging: loaded {len(actions)} pg(s) for {process_id} "
                f"into RAM on Ready"
            ),
            "steps": [
                f"{process_id} entered Ready Queue",
                f"Prepaging loaded {len(actions)} page(s) into free frames",
                *[
                    f"  {process_id}:pg{a['page']} -> Frame {a['frame']}"
                    for a in actions
                ],
            ],
        }
        self._log(self.last_memory_event["message"], "prepage")

    def _release_process_memory(self, process_id: str) -> None:
        """Reclaim RAM frames/segments after process termination."""
        if self.memory_scheme == "Segmentation":
            actions = self.segments.release_process(process_id)
            if not actions:
                return
            self.last_memory_event = {
                "result": "RELEASE",
                "scheme": "Segmentation",
                "process_id": process_id,
                "name": actions[0].get("name"),
                "message": (
                    f"{process_id} terminated — released {len(actions)} "
                    f"segment(s) from RAM"
                ),
                "steps": [
                    f"{process_id} finished execution",
                    "OS frees the process address space",
                    *[
                        f"  OUT {process_id}:{a['name']} (base {a['base']})"
                        for a in actions
                    ],
                ],
            }
        else:
            actions = self.memory.release_process(process_id)
            if not actions:
                return
            self.last_memory_event = {
                "result": "RELEASE",
                "scheme": "Paging",
                "process_id": process_id,
                "page": actions[0]["page"],
                "frame": actions[0]["frame"],
                "message": (
                    f"{process_id} terminated — released {len(actions)} "
                    f"page(s) from RAM"
                ),
                "steps": [
                    f"{process_id} finished execution",
                    "OS frees the process address space",
                    *[
                        f"  OUT {process_id}:pg{a['page']} <- Frame {a['frame']}"
                        for a in actions
                    ],
                ],
            }
        self._log(self.last_memory_event["message"], "release")

    def set_replacement_algorithm(self, algorithm: str) -> None:
        self.replacement_algorithm = algorithm
        self._log(f"Page replacement algorithm = {algorithm}", "config")

    def set_page_references(self, references: list[int]) -> None:
        self.page_reference_string = list(references)
        self.reference_index = 0
        self._log(f"Page reference string loaded ({len(references)} refs)", "config")

    def configure_raid(self, level: str, disk_count: int) -> None:
        if not self.raid.logical_blocks:
            self.raid.configure(level, disk_count)
            self._store_all_blocks_on_raid(replace=True)
        else:
            self.raid.configure(level, disk_count)
        self._log(self.raid.last_event, "raid")

    def reset(self) -> None:
        self.cpu.reset()
        self._sync_memory_tables()
        self.reference_index = 0
        self.last_memory_event = None
        self.peak_memory = {}
        self.last_memory_map = None
        self._store_all_blocks_on_raid(replace=True)
        self._raid_finalized = False
        self.kernel_log = []
        self._log("Simulation reset", "control")

    def reset_to_defaults(self) -> None:
        """Full factory reset: empty workload and default OS settings."""
        from .research_process import ResearchWorkload

        self.memory_scheme = "Paging"
        self.virtual_memory_kb = 64
        self.replacement_algorithm = "FIFO"
        self.page_reference_string = list(DEFAULT_PAGE_REFERENCES)
        self.reference_index = 0
        self.last_memory_event = None
        self.scheme_run_stats = {}
        self.peak_memory = {}
        self.last_memory_map = None
        self.last_run = None
        self._raid_finalized = False
        self.kernel_log = []
        self.paging_mode = "Demand paging"
        self.memory.reconfigure(32, 4, frame_size_kb=4, frame_count=8)
        self.segments.reconfigure(32)
        self.raid.configure("RAID 5", 4)
        self.cpu.page_size_kb = 4
        self.cpu.set_scheduling_policy("FCFS", time_quantum=4, processor_count=1)
        self.load_workload(
            ResearchWorkload(
                name="Custom Research Workload",
                scenario="User-defined research jobs on the HPC node",
                processes=[],
            )
        )
        self._log("Factory reset — defaults restored", "control")

    def _memory_metrics(self) -> dict:
        if self.memory_scheme == "Segmentation":
            return self.segments.metrics()
        return self.memory.metrics()

    def _capture_memory_map(self) -> None:
        """Merge resident table rows so finished processes keep their last mapping."""
        snap = self._active_memory_snapshot()
        metrics = snap.get("metrics") or {}
        if self.memory_scheme == "Paging":
            if not metrics.get("pages_in_ram"):
                return
            prev_tables = (self.last_memory_map or {}).get("page_tables", {})
            merged: dict[str, list] = {}
            for pid, rows in (snap.get("page_tables") or {}).items():
                prev_by_page = {r["page"]: r for r in prev_tables.get(pid, [])}
                merged_rows = []
                for row in rows:
                    if row.get("valid_bit") == 1:
                        merged_rows.append(deepcopy(row))
                    elif prev_by_page.get(row["page"], {}).get("valid_bit") == 1:
                        merged_rows.append(deepcopy(prev_by_page[row["page"]]))
                    else:
                        merged_rows.append(deepcopy(row))
                merged[pid] = merged_rows
            # Keep prior processes that already finished (no longer in live tables).
            for pid, rows in prev_tables.items():
                if pid not in merged:
                    merged[pid] = deepcopy(rows)
            self.last_memory_map = {
                "scheme": "Paging",
                "at_time": self.cpu.current_time,
                "frames": deepcopy(snap.get("frames", [])),
                "page_tables": merged,
                "note": "Last known page-table residency during the run",
            }
        else:
            if not metrics.get("ram_used_kb"):
                return
            prev_tables = (self.last_memory_map or {}).get("segment_tables", {})
            merged = {}
            for pid, rows in (snap.get("segment_tables") or {}).items():
                prev_by_id = {r.get("segment"): r for r in prev_tables.get(pid, [])}
                merged_rows = []
                for row in rows:
                    if row.get("valid_bit") == 1:
                        merged_rows.append(deepcopy(row))
                    elif prev_by_id.get(row.get("segment"), {}).get("valid_bit") == 1:
                        merged_rows.append(deepcopy(prev_by_id[row.get("segment")]))
                    else:
                        merged_rows.append(deepcopy(row))
                merged[pid] = merged_rows
            for pid, rows in prev_tables.items():
                if pid not in merged:
                    merged[pid] = deepcopy(rows)
            self.last_memory_map = {
                "scheme": "Segmentation",
                "at_time": self.cpu.current_time,
                "regions": deepcopy(snap.get("regions", [])),
                "segment_tables": merged,
                "note": "Last known segment-table residency during the run",
            }

    def _update_peak_memory(self) -> None:
        """Track highest occupancy during the run (before frames are freed)."""
        mem = self._memory_metrics()
        used = mem.get("pages_in_ram", 0) if self.memory_scheme == "Paging" else mem.get(
            "ram_used_kb", 0
        )
        prev = self.peak_memory.get(
            "_rank", -1
        )
        rank = used
        # Refresh Memory-page map while anything is resident (merge keeps history).
        if rank > 0:
            self._capture_memory_map()
        if rank < prev:
            return
        self.peak_memory = {
            "_rank": rank,
            "memory_utilisation": mem.get("memory_utilisation", 0),
            "pages_in_ram": mem.get("pages_in_ram", 0),
            "frames_total": mem.get("frames_total", 0),
            "frames_free": mem.get("frames_free", 0),
            "ram_used_kb": mem.get("ram_used_kb", 0),
            "ram_size_kb": mem.get("ram_size_kb", 0),
            "ram_free_kb": mem.get("ram_free_kb", 0),
        }

    def _record_scheme_stats(self) -> None:
        mem = self._memory_metrics()
        peak = self.peak_memory or {}
        self.scheme_run_stats[self.memory_scheme] = {
            "scheme": self.memory_scheme,
            "faults": mem.get("page_faults", 0),
            "hits": mem.get("page_hits", 0),
            "fault_rate": mem.get("page_fault_rate", 0),
            "hit_rate": mem.get("page_hit_rate", 0),
            "replacements": mem.get("page_replacements", 0),
            "transfers": mem.get("pages_transferred", 0),
            "memory_utilisation": peak.get(
                "memory_utilisation", mem.get("memory_utilisation", 0)
            ),
            "peak_frames_used": peak.get("pages_in_ram", mem.get("pages_in_ram", 0)),
            "peak_ram_used_kb": peak.get("ram_used_kb", mem.get("ram_used_kb", 0)),
            "internal_fragmentation_kb": mem.get("internal_fragmentation_kb", 0),
            "external_fragmentation_kb": mem.get("external_fragmentation_kb", 0),
            "external_fragmentation_pct": mem.get("external_fragmentation_pct", 0),
            "allocation_failures": mem.get("allocation_failures", 0),
            "free_holes": mem.get("free_holes", 0),
        }

    def _save_last_run(self) -> None:
        """Freeze Metrics-page dashboard for the completed run."""
        cpu_snap = self.cpu.snapshot()
        mem = dict(self._memory_metrics())
        peak = self.peak_memory or {}
        if peak:
            mem["memory_utilisation"] = peak.get(
                "memory_utilisation", mem.get("memory_utilisation", 0)
            )
            mem["pages_in_ram"] = peak.get("pages_in_ram", mem.get("pages_in_ram", 0))
            mem["frames_free"] = peak.get("frames_free", mem.get("frames_free", 0))
            mem["ram_used_kb"] = peak.get("ram_used_kb", mem.get("ram_used_kb", 0))
            mem["ram_free_kb"] = peak.get("ram_free_kb", mem.get("ram_free_kb", 0))
            if peak.get("frames_total") is not None:
                mem["frames_total"] = peak["frames_total"]
            if peak.get("ram_size_kb") is not None:
                mem["ram_size_kb"] = peak["ram_size_kb"]
        mem["usage_basis"] = "peak_during_run"
        raid = self.raid.metrics()
        virtual_pages = max(1, self.virtual_memory_kb // self.memory.page_size_kb)
        self.last_run = {
            "completed_at_time": cpu_snap["current_time"],
            "workload_name": cpu_snap["workload_name"],
            "scheduling_policy": cpu_snap["scheduling_policy"],
            "memory_scheme": self.memory_scheme,
            "paging_mode": self.paging_mode,
            "replacement_algorithm": self.replacement_algorithm,
            "dashboard": {
                "cpu": cpu_snap["metrics"],
                "memory": mem,
                "virtual_memory": {
                    "pages_in_ram": mem.get("pages_in_ram", 0),
                    "pages_on_secondary_storage": mem.get("pages_on_disk", 0),
                    "page_transfer_count": mem.get("pages_transferred", 0),
                    "replacement_count": mem.get("page_replacements", 0),
                    "virtual_pages": virtual_pages,
                    "physical_frames": self.memory.frame_count,
                    "scheme": self.memory_scheme,
                },
                "raid": raid,
            },
            "kernel_log": list(self.kernel_log[-40:]),
        }

    def step(self) -> dict:
        """
        One observable OS event:
        1) admit/dispatch/execute CPU tick when needed
        2) if a process is running, consume next memory reference
        """
        if not self.cpu.is_complete:
            self.cpu.step()

        # Capture occupancy before terminated processes free their frames.
        self._update_peak_memory()

        # Tear down address space first so freed frames can be reused.
        if self.cpu.last_terminated:
            for pid in self.cpu.last_terminated:
                self._release_process_memory(pid)

        # Prepaging: bring pages into RAM when process enters Ready.
        if (
            self.memory_scheme == "Paging"
            and self.paging_mode == "Prepaging"
            and self.cpu.last_admitted
        ):
            for pid in self.cpu.last_admitted:
                self._prepage_process(pid)
            self._update_peak_memory()

        running = self.cpu.running_process
        if running is not None and self.reference_index < len(self.page_reference_string):
            ref = self.page_reference_string[self.reference_index]
            if self.memory_scheme == "Segmentation":
                self._step_segmentation(running.process_id, ref)
            else:
                self._step_paging(running.process_id, ref)
            self.reference_index += 1
            self._update_peak_memory()

        if self.cpu.is_complete and not self._raid_finalized:
            self._store_all_blocks_on_raid(replace=True)
            self._raid_finalized = True
            self._record_scheme_stats()
            self._save_last_run()
            self._log(
                f"Run complete — blocks stored with {self.raid.level} "
                f"under {self.memory_scheme}",
                "raid",
            )

        return self.snapshot()

    def _step_paging(self, process_id: str, page: int) -> None:
        future = [
            (process_id, ref)
            for ref in self.page_reference_string[self.reference_index + 1 :]
        ]
        table = self.memory.page_tables.get(process_id, [])
        if table:
            page = page % len(table)
        memory_event = self.memory.access_page(
            process_id,
            page,
            write=False,
            replacement_algo=self.replacement_algorithm,
            future_refs=future,
        )
        memory_event["scheme"] = "Paging"
        self.last_memory_event = memory_event
        block = f"{process_id}:pg{page}"
        if memory_event["result"] == "FAULT":
            self.raid.store_blocks([block])
            self.raid.read_block(block)
            if memory_event.get("victim"):
                victim = memory_event["victim"]
                victim_block = f"{victim['process_id']}:pg{victim['page']}"
                self.raid.store_blocks([victim_block])
            self._log(memory_event["message"], "fault")
            for step_msg in memory_event["steps"]:
                self._log(step_msg, "fault-step")
            self._log(self.raid.last_event, "raid")
        else:
            self._log(memory_event["message"], "hit")

    def _step_segmentation(self, process_id: str, ref: int) -> None:
        table = self.segments.segment_tables.get(process_id, [])
        if not table:
            return
        segment_id = ref % len(table)
        memory_event = self.segments.access_segment(process_id, segment_id)
        self.last_memory_event = memory_event
        entry = table[segment_id]
        block = f"{process_id}:{entry.name}"
        if memory_event["result"] == "FAULT":
            self.raid.store_blocks([block])
            self.raid.read_block(block)
            if memory_event.get("victim"):
                victim = memory_event["victim"]
                victim_block = f"{victim['process_id']}:{victim['name']}"
                self.raid.store_blocks([victim_block])
            self._log(memory_event["message"], "fault")
            for step_msg in memory_event["steps"]:
                self._log(step_msg, "fault-step")
            self._log(self.raid.last_event, "raid")
        else:
            self._log(memory_event["message"], "hit")

    def run_page_trace(self) -> dict:
        """Run remaining memory references for the active workload."""
        guard = 0
        while (
            self.reference_index < len(self.page_reference_string)
            and not self.cpu.is_complete
            and guard < 5000
        ):
            self.step()
            guard += 1
        self._record_scheme_stats()
        return self.snapshot()

    def compare_replacement(self) -> dict:
        frames = max(1, self.memory.frame_count)
        return compare_algorithms(self.page_reference_string, frames)

    def compare_memory_schemes(self) -> dict:
        return {
            "active_scheme": self.memory_scheme,
            "runs": self.scheme_run_stats,
            "note": (
                "Run the same workload once under Paging and once under "
                "Segmentation to fill both columns."
            ),
        }

    def _active_memory_snapshot(self) -> dict:
        if self.memory_scheme == "Segmentation":
            return self.segments.snapshot()
        return self.memory.snapshot()

    def snapshot(self) -> dict:
        cpu_snap = self.cpu.snapshot()
        mem_snap = self._active_memory_snapshot()
        # Keep paging snapshot available for virtual-memory page tools.
        paging_snap = self.memory.snapshot()
        raid_snap = self.raid.snapshot()
        virtual_pages = max(1, self.virtual_memory_kb // self.memory.page_size_kb)
        return {
            "workload_name": cpu_snap["workload_name"],
            "scenario": cpu_snap["scenario"],
            "memory_scheme": self.memory_scheme,
            "memory_schemes": list(MEMORY_SCHEMES),
            "paging_mode": self.paging_mode,
            "paging_modes": list(PAGING_MODES),
            "virtual_memory_kb": self.virtual_memory_kb,
            "virtual_pages": virtual_pages,
            "physical_frames": self.memory.frame_count,
            "replacement_algorithm": self.replacement_algorithm,
            "page_reference_string": self.page_reference_string,
            "reference_index": self.reference_index,
            "last_memory_event": self.last_memory_event,
            "scheme_comparison": self.compare_memory_schemes(),
            "last_run": self.last_run,
            "last_memory_map": self.last_memory_map,
            "peak_memory": {
                k: v for k, v in self.peak_memory.items() if not k.startswith("_")
            },
            "cpu": cpu_snap,
            "memory": mem_snap,
            "paging": paging_snap,
            "raid": raid_snap,
            "kernel_log": self.kernel_log[-40:],
            "dashboard": {
                "cpu": cpu_snap["metrics"],
                "memory": mem_snap["metrics"],
                "virtual_memory": {
                    "pages_in_ram": mem_snap["metrics"]["pages_in_ram"],
                    "pages_on_secondary_storage": mem_snap["metrics"]["pages_on_disk"],
                    "page_transfer_count": mem_snap["metrics"]["pages_transferred"],
                    "replacement_count": mem_snap["metrics"]["page_replacements"],
                    "virtual_pages": virtual_pages,
                    "physical_frames": self.memory.frame_count,
                    "scheme": self.memory_scheme,
                },
                "raid": raid_snap["metrics"],
            },
            "concept_notes": CONCEPT_NOTES,
        }


CONCEPT_NOTES = {
    "scheduling": (
        "CPU scheduling selects which ready process runs next. Non-preemptive "
        "policies (FCFS, SJF, Priority) run until the burst ends; Round Robin "
        "preempts after a time quantum so interactive research jobs share the CPU "
        "(see Stallings, process/CPU scheduling chapters)."
    ),
    "paging": (
        "Paging splits each process into fixed-size pages and main memory into "
        "frames of the same size. The page table records frame number, valid bit "
        "and dirty bit so the MMU can translate virtual addresses "
        "(Stallings, memory management / paging)."
    ),
    "demand_paging": (
        "Demand paging loads a page into RAM only when the CPU references it "
        "(page fault). A Ready process may have no pages resident yet."
    ),
    "prepaging": (
        "Prepaging loads pages into free frames when a process enters the Ready "
        "queue, so more of the working set is resident before the CPU runs it "
        "(Stallings contrast to pure demand paging)."
    ),
    "relocation": (
        "Relocation maps a process's logical addresses to physical addresses at "
        "run time. In paging: physical = frame×page_size + offset. In segmentation: "
        "physical = base + offset (with a limit check). The same logical page can "
        "later reside in a different frame after replacement "
        "(Stallings, memory management — relocation)."
    ),
    "segmentation": (
        "Segmentation splits a process into variable-sized logical segments "
        "(e.g. Code, Data, Stack). Each segment needs a contiguous region of RAM. "
        "This avoids internal fragmentation of fixed pages but can cause external "
        "fragmentation when free holes are too small for a requested segment "
        "(Stallings, memory management / segmentation)."
    ),
    "page_fault": (
        "A page fault occurs when the CPU references a page whose valid bit is 0. "
        "The OS locates the page on secondary storage, selects a free frame or a "
        "victim page, loads the page, updates the page table, then resumes the process."
    ),
    "virtual_memory": (
        "Virtual memory lets a process use an address space larger than physical "
        "RAM. Only the working set of pages must be resident; others stay on disk "
        "until referenced (Stallings, virtual memory)."
    ),
    "replacement": (
        "FIFO replaces the oldest resident page; LRU replaces the least recently "
        "used page; Optimal replaces the page that will not be needed for the "
        "longest time in the future (Belady). Optimal is a benchmark, not always "
        "implementable without future knowledge."
    ),
    "raid": (
        "RAID aggregates disks for performance and/or reliability. RAID 0 stripes "
        "with no redundancy; RAID 1 mirrors; RAID 5/6 add parity; RAID 10 stripes "
        "mirrors. After a disk failure, levels with redundancy can reconstruct data "
        "(Stallings, secondary storage / I/O)."
    ),
}
