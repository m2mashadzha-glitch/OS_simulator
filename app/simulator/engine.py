from __future__ import annotations

from typing import List, Optional

from .memory import MemoryManager
from .process import Process
from .raid import RAIDController
from .scheduler import Scheduler


DEFAULT_PROCESSES = [
    {"pid": "P1", "arrival": 0, "burst": 8, "priority": 2, "size_kb": 12},
    {"pid": "P2", "arrival": 1, "burst": 5, "priority": 1, "size_kb": 8},
    {"pid": "P3", "arrival": 2, "burst": 12, "priority": 3, "size_kb": 20},
    {"pid": "P4", "arrival": 3, "burst": 6, "priority": 2, "size_kb": 16},
    {"pid": "P5", "arrival": 4, "burst": 10, "priority": 4, "size_kb": 24},
]

DEMO_PAGE_REFS = [
    0, 1, 2, 3, 4, 5, 0, 1, 6, 7,
    2, 3, 8, 9, 0, 1, 4, 5, 10, 11,
]


class SimulationEngine:
    """Integrates CPU scheduling, paging, virtual memory and RAID."""

    def __init__(self) -> None:
        self.scheduler = Scheduler("FCFS", quantum=4)
        self.memory = MemoryManager(ram_size_kb=32, page_size_kb=4, virtual_size_kb=64)
        self.raid = RAIDController(level="RAID 5", num_disks=4)
        self.processes: List[Process] = []
        self.ready: List[Process] = []
        self.running: Optional[Process] = None
        self.waiting: List[Process] = []
        self.completed: List[Process] = []
        self.time = 0
        self.busy_time = 0
        self.gantt: List[dict] = []
        self.event_log: List[str] = []
        self.running_auto = False
        self._load_default_processes()

    def _log(self, message: str) -> None:
        self.event_log.append(f"t={self.time}: {message}")
        if len(self.event_log) > 200:
            self.event_log = self.event_log[-200:]

    def _load_default_processes(self) -> None:
        self.processes = [
            Process(
                pid=p["pid"],
                arrival=p["arrival"],
                burst=p["burst"],
                priority=p["priority"],
                size_kb=p["size_kb"],
                page_size_kb=self.memory.page_size_kb,
            )
            for p in DEFAULT_PROCESSES
        ]
        for proc in self.processes:
            self.memory.ensure_process(proc.pid, proc.num_pages)

    def configure(
        self,
        algorithm: Optional[str] = None,
        quantum: Optional[int] = None,
        ram_size_kb: Optional[int] = None,
        page_size_kb: Optional[int] = None,
        virtual_size_kb: Optional[int] = None,
        replacement: Optional[str] = None,
        raid_level: Optional[str] = None,
        num_disks: Optional[int] = None,
    ) -> None:
        if algorithm:
            self.scheduler.algorithm = algorithm
        if quantum is not None:
            self.scheduler.quantum = max(1, quantum)
        if any(v is not None for v in (ram_size_kb, page_size_kb, virtual_size_kb, replacement)):
            self.memory.reconfigure(
                ram_size_kb or self.memory.ram_size_kb,
                page_size_kb or self.memory.page_size_kb,
                virtual_size_kb or self.memory.virtual_size_kb,
                replacement or self.memory.replacement,
            )
            for proc in self.processes:
                proc.page_size_kb = self.memory.page_size_kb
                self.memory.ensure_process(proc.pid, proc.num_pages)
        if raid_level or num_disks:
            self.raid.reset(raid_level, num_disks)

    def reset(self) -> None:
        algo = self.scheduler.algorithm
        quantum = self.scheduler.quantum
        mem = (
            self.memory.ram_size_kb,
            self.memory.page_size_kb,
            self.memory.virtual_size_kb,
            self.memory.replacement,
        )
        raid_level = self.raid.level
        disks = self.raid.num_disks
        self.__init__()
        self.configure(
            algorithm=algo,
            quantum=quantum,
            ram_size_kb=mem[0],
            page_size_kb=mem[1],
            virtual_size_kb=mem[2],
            replacement=mem[3],
            raid_level=raid_level,
            num_disks=disks,
        )
        self._log("Simulation reset")

    def generate_processes(self) -> None:
        self.reset()
        self._log("Generated default process set (P1–P5)")

    def load_demo_scenario(self) -> None:
        """Required assessment scenario: large research process."""
        self.scheduler = Scheduler("Round Robin", quantum=4)
        self.memory = MemoryManager(
            ram_size_kb=16,
            page_size_kb=4,
            virtual_size_kb=64,
            replacement="LRU",
        )
        self.memory.future_refs = list(DEMO_PAGE_REFS)
        self.raid = RAIDController(level="RAID 5", num_disks=4)
        self.processes = [
            Process(
                pid="P_RESEARCH",
                arrival=0,
                burst=len(DEMO_PAGE_REFS),
                priority=1,
                size_kb=48,
                page_size_kb=4,
                page_refs=list(DEMO_PAGE_REFS),
            )
        ]
        self.ready = []
        self.running = None
        self.waiting = []
        self.completed = []
        self.time = 0
        self.busy_time = 0
        self.gantt = []
        self.event_log = []
        self.memory.ensure_process("P_RESEARCH", self.processes[0].num_pages)
        # Seed secondary storage via RAID for all virtual pages
        for page in range(self.processes[0].num_pages):
            self.raid.write_page("P_RESEARCH", page)
        self._log(
            "Loaded demo scenario: 48KB process, 16KB RAM, 64KB virtual, "
            "4KB pages, RAID 5 with 4 disks"
        )

    def generate_page_references(self, refs: Optional[List[int]] = None) -> None:
        refs = refs or DEMO_PAGE_REFS
        self.memory.future_refs = list(refs)
        self.memory.future_index = 0
        if self.running:
            self.running.page_refs = list(refs)
            self.running.ref_index = 0
        elif self.processes:
            self.processes[0].page_refs = list(refs)
            self.processes[0].ref_index = 0
        self._log(f"Page reference string set ({len(refs)} refs)")

    def _admit_arrivals(self) -> None:
        for proc in self.processes:
            if proc.status == "New" and proc.arrival <= self.time:
                proc.status = "Ready"
                self.ready.append(proc)
                self.memory.ensure_process(proc.pid, proc.num_pages)
                self._log(f"{proc.pid} enters Ready Queue")

    def _update_waiting_times(self) -> None:
        for proc in self.ready:
            proc.waiting_time += 1

    def _dispatch(self) -> None:
        if self.running is not None:
            return
        nxt = self.scheduler.select(self.ready)
        if not nxt:
            return
        self.ready.remove(nxt)
        nxt.status = "Running"
        nxt.quantum_used = 0
        if nxt.first_response_time is None:
            nxt.first_response_time = self.time
        if nxt.start_time is None:
            nxt.start_time = self.time
        self.running = nxt
        self._log(f"{nxt.pid} allocated to CPU")

    def _handle_memory_for_running(self) -> None:
        assert self.running is not None
        page = self.running.next_page_ref()
        if page is None:
            return
        # Ensure page exists in secondary storage
        key = f"{self.running.pid}:P{page}"
        if key not in self.raid.stored_pages:
            self.raid.write_page(self.running.pid, page)
        event = self.memory.access(self.running.pid, page, self.time)
        if event["type"] == "PAGE_FAULT":
            self.raid.read_page(self.running.pid, page)
            self._log(
                f"PAGE FAULT: {self.running.pid} page {page} → Frame {event.get('frame')}"
            )
        else:
            self._log(f"PAGE HIT: {self.running.pid} page {page}")

    def _preempt_rr_if_needed(self) -> None:
        if (
            self.running
            and self.scheduler.algorithm == "Round Robin"
            and self.running.remaining
            and self.running.remaining > 0
            and self.running.quantum_used >= self.scheduler.quantum
        ):
            self.running.status = "Ready"
            self.running.quantum_used = 0
            self.ready.append(self.running)
            self._log(f"{self.running.pid} quantum expired → Ready Queue")
            self.running = None

    def step(self) -> dict:
        if all(p.status == "Terminated" for p in self.processes) and self.processes:
            self._log("All processes terminated")
            return self.state()

        self._admit_arrivals()
        self._dispatch()

        if self.running:
            self._handle_memory_for_running()
            self.running.remaining = max(0, (self.running.remaining or 0) - 1)
            self.running.quantum_used += 1
            self.busy_time += 1
            self.gantt.append({"time": self.time, "pid": self.running.pid})
            self._log(
                f"{self.running.pid} running (remaining={self.running.remaining})"
            )

            if self.running.remaining == 0:
                self.running.status = "Terminated"
                self.running.finish_time = self.time + 1
                self.completed.append(self.running)
                self._log(f"{self.running.pid} terminated")
                self.running = None
            else:
                self._preempt_rr_if_needed()
        else:
            self.gantt.append({"time": self.time, "pid": "IDLE"})
            self._log("CPU idle")

        self._update_waiting_times()
        self.time += 1
        # Admit anyone arriving at the new time boundary for snappier UI
        self._admit_arrivals()
        return self.state()

    def run_for(self, steps: int = 1) -> dict:
        for _ in range(max(1, steps)):
            if all(p.status == "Terminated" for p in self.processes) and self.processes:
                break
            self.step()
        return self.state()

    def fail_disk(self, disk_id: int = 2) -> dict:
        event = self.raid.fail_disk(disk_id)
        self._log(
            f"DISK FAILURE DETECTED – Disk {disk_id}; "
            f"data available={event.get('data_available')}"
        )
        return self.state()

    def recover_disk(self, disk_id: int = 2) -> dict:
        event = self.raid.recover_disk(disk_id)
        self._log(event.get("message", "Recovery attempted"))
        return self.state()

    def metrics(self) -> dict:
        finished = [p for p in self.processes if p.finish_time is not None]
        n = len(finished)
        avg_wait = sum(p.waiting_time for p in finished) / n if n else 0
        avg_tat = sum(p.turnaround_time or 0 for p in finished) / n if n else 0
        avg_resp = sum(p.response_time or 0 for p in finished) / n if n else 0
        util = (self.busy_time / self.time * 100) if self.time else 0
        return {
            "cpu_utilisation": round(util, 2),
            "average_waiting_time": round(avg_wait, 2),
            "average_turnaround_time": round(avg_tat, 2),
            "average_response_time": round(avg_resp, 2),
            "current_time": self.time,
            "busy_time": self.busy_time,
            "completed_count": n,
        }

    def compare_replacement(self, refs: Optional[List[int]] = None) -> List[dict]:
        """Offline comparison of FIFO / LRU / Optimal on the same reference string."""
        refs = refs or DEMO_PAGE_REFS
        results = []
        frames = self.memory.num_frames
        for algo in ("FIFO", "LRU", "Optimal"):
            mm = MemoryManager(
                ram_size_kb=self.memory.ram_size_kb,
                page_size_kb=self.memory.page_size_kb,
                virtual_size_kb=self.memory.virtual_size_kb,
                replacement=algo,
            )
            mm.future_refs = list(refs)
            mm.ensure_process("CMP", max(refs) + 1 if refs else 1)
            for r in refs:
                mm.access("CMP", r, mm.future_index)
            results.append(
                {
                    "algorithm": algo,
                    "frames": frames,
                    "references": len(refs),
                    "hits": mm.page_hits,
                    "faults": mm.page_faults,
                    "hit_rate": round(mm.hit_rate(), 2),
                    "fault_rate": round(mm.fault_rate(), 2),
                }
            )
        return results

    def state(self) -> dict:
        return {
            "time": self.time,
            "scheduler": self.scheduler.to_dict(),
            "running": self.running.to_dict() if self.running else None,
            "ready": [p.to_dict() for p in self.ready],
            "waiting": [p.to_dict() for p in self.waiting],
            "completed": [p.to_dict() for p in self.completed],
            "processes": [p.to_dict() for p in self.processes],
            "gantt": self.gantt[-80:],
            "event_log": self.event_log[-40:],
            "memory": self.memory.to_dict(),
            "raid": self.raid.to_dict(),
            "metrics": self.metrics(),
            "replacement_comparison": self.compare_replacement(
                self.memory.future_refs or DEMO_PAGE_REFS
            ),
        }
