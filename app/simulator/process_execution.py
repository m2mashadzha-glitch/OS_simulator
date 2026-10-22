"""Part A — Process execution and CPU management for the research centre."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from .cpu_scheduler import CpuScheduler, SchedulingPolicy, build_scheduler
from .gantt_chart import GanttChart
from .ready_queue import ReadyQueue
from .research_process import ProcessState, ResearchProcess, ResearchWorkload


@dataclass
class ExecutionEvent:
    time: int
    kind: str
    message: str
    process_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "kind": self.kind,
            "message": self.message,
            "process_id": self.process_id,
        }


@dataclass
class ProcessExecutionEngine:
    workload_name: str = "Research Centre Baseline Workload"
    scenario: str = (
        "University research centre HPC node — competing research applications"
    )
    scheduling_policy: SchedulingPolicy = SchedulingPolicy.FCFS
    time_quantum: int = 4
    page_size_kb: int = 4
    processor_count: int = 1

    current_time: int = 0
    busy_ticks: int = 0
    is_running: bool = False
    is_complete: bool = False
    just_completed: bool = False

    processes: list[ResearchProcess] = field(default_factory=list)
    ready_queue: ReadyQueue = field(default_factory=ReadyQueue)
    # One slot per CPU (None = idle)
    running_slots: list[ResearchProcess | None] = field(default_factory=list)
    completed_processes: list[ResearchProcess] = field(default_factory=list)
    waiting_processes: list[ResearchProcess] = field(default_factory=list)
    gantt: GanttChart = field(default_factory=GanttChart)
    event_log: list[ExecutionEvent] = field(default_factory=list)

    _scheduler: CpuScheduler = field(init=False, repr=False)
    _original_processes: list[ResearchProcess] = field(
        default_factory=list, repr=False
    )
    _quantum_remaining: list[int] = field(default_factory=list, repr=False)
    _submitted_ids: set[str] = field(default_factory=set, repr=False)
    last_admitted: list[str] = field(default_factory=list)
    last_terminated: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.processor_count = max(1, min(8, int(self.processor_count)))
        self._scheduler = build_scheduler(
            self.scheduling_policy,
            time_quantum=self.time_quantum,
        )
        self._ensure_slots()

    def _ensure_slots(self) -> None:
        n = self.processor_count
        if len(self.running_slots) != n:
            self.running_slots = [None] * n
        if len(self._quantum_remaining) != n:
            self._quantum_remaining = [0] * n

    @property
    def running_process(self) -> ResearchProcess | None:
        """Primary running process (first busy CPU) — for single-CPU callers."""
        for process in self.running_slots:
            if process is not None:
                return process
        return None

    @property
    def running_processes(self) -> list[ResearchProcess]:
        return [process for process in self.running_slots if process is not None]

    def load_workload(self, workload: ResearchWorkload) -> None:
        self.workload_name = workload.name
        self.scenario = workload.scenario
        self._original_processes = deepcopy(workload.processes)
        for process in self._original_processes:
            process.page_size_kb = self.page_size_kb
        self.reset()

    def load_process_dicts(self, process_dicts: list[dict]) -> None:
        processes = [
            ResearchProcess(
                process_id=str(item["process_id"]).strip(),
                arrival_time=int(item["arrival_time"]),
                burst_time=int(item["burst_time"]),
                priority=int(item["priority"]),
                memory_requirement_kb=int(
                    item.get("memory_requirement_kb", item.get("process_size_kb", 0))
                ),
                process_size_kb=int(item["process_size_kb"]),
                page_size_kb=self.page_size_kb,
                description=str(item.get("description", "")),
            )
            for item in process_dicts
        ]
        self.load_workload(
            ResearchWorkload(
                name=self.workload_name,
                scenario=self.scenario,
                processes=processes,
            )
        )

    def export_workload(self) -> ResearchWorkload:
        return ResearchWorkload(
            name=self.workload_name,
            scenario=self.scenario,
            processes=deepcopy(self._original_processes),
        )

    def set_processor_count(self, count: int) -> None:
        count = max(1, min(8, int(count)))
        if count == self.processor_count:
            return
        self.processor_count = count
        self.reset()
        self._log(
            self.current_time,
            "config",
            f"Processor count set to {self.processor_count}",
        )

    def set_scheduling_policy(
        self,
        policy: SchedulingPolicy | str,
        time_quantum: int | None = None,
        processor_count: int | None = None,
    ) -> None:
        if time_quantum is not None:
            self.time_quantum = time_quantum
        if processor_count is not None:
            self.processor_count = max(1, min(8, int(processor_count)))
        self.scheduling_policy = (
            policy
            if isinstance(policy, SchedulingPolicy)
            else build_scheduler(policy, self.time_quantum).policy
        )
        self._scheduler = build_scheduler(
            self.scheduling_policy,
            time_quantum=self.time_quantum,
        )
        self.reset()

    def reset(self) -> None:
        self.current_time = 0
        self.busy_ticks = 0
        self.is_running = False
        self.is_complete = False
        self.just_completed = False
        self.ready_queue.clear()
        self._ensure_slots()
        self.running_slots = [None] * self.processor_count
        self.completed_processes = []
        self.waiting_processes = []
        self.gantt.clear()
        self.event_log = []
        self._quantum_remaining = [0] * self.processor_count
        self._submitted_ids = set()
        self.last_admitted = []
        self.last_terminated = []
        self.processes = deepcopy(self._original_processes)
        for process in self.processes:
            process.status = ProcessState.NEW
            process.remaining_burst = process.burst_time
            process.start_time = None
            process.finish_time = None
            process.response_time = None
            process.waiting_time = 0
            process.turnaround_time = 0
            process.last_ready_time = process.arrival_time
        self._log(0, "reset", "Simulation reset — research workload reloaded")

    def start(self) -> dict:
        self.is_running = True
        self._log(self.current_time, "control", "Simulation started")
        return self.snapshot()

    def pause(self) -> dict:
        self.is_running = False
        self._log(self.current_time, "control", "Simulation paused")
        return self.snapshot()

    def step(self) -> dict:
        if self.is_complete:
            return self.snapshot()

        self.last_admitted = []
        self.last_terminated = []
        self._admit_arrivals()
        self._dispatch_idle_cpus()

        any_busy = any(slot is not None for slot in self.running_slots)
        if any_busy:
            self._execute_one_tick_all()
        else:
            for cpu_id in range(self.processor_count):
                self.gantt.note_activity(self.current_time, None, cpu_id=cpu_id)
            self.current_time += 1

        # Terminations/preemptions free slots at end of the tick. Admit any
        # arrivals at the new time and refill idle CPUs so the snapshot never
        # shows idle processors while the Ready Queue still has work.
        self._admit_arrivals()
        self._dispatch_idle_cpus()

        self._check_completion()
        return self.snapshot()

    def run_to_completion(self, max_ticks: int = 10_000) -> dict:
        self.is_running = True
        ticks = 0
        while not self.is_complete and ticks < max_ticks:
            self.step()
            ticks += 1
        self.is_running = False
        return self.snapshot()

    def _admit_arrivals(self) -> None:
        for process in self.processes:
            if (
                process.process_id not in self._submitted_ids
                and process.arrival_time <= self.current_time
                and process.status is ProcessState.NEW
            ):
                process.mark_ready(self.current_time)
                self.ready_queue.enqueue(process)
                self._submitted_ids.add(process.process_id)
                self.last_admitted.append(process.process_id)
                self._log(
                    self.current_time,
                    "arrival",
                    f"{process.process_id} enters Ready Queue "
                    f"({process.description or 'research job'})",
                    process.process_id,
                )

    def _dispatch_idle_cpus(self) -> None:
        for cpu_id, slot in enumerate(self.running_slots):
            if slot is not None:
                continue
            selected = self._scheduler.select(self.ready_queue)
            if selected is None:
                return
            selected.mark_running(self.current_time)
            self.running_slots[cpu_id] = selected
            if self._scheduler.uses_time_quantum:
                self._quantum_remaining[cpu_id] = self.time_quantum
            self._log(
                self.current_time,
                "dispatch",
                f"{selected.process_id} allocated to CPU{cpu_id + 1} "
                f"under {self._scheduler.policy.value}",
                selected.process_id,
            )

    def _execute_one_tick_all(self) -> None:
        # Record activity and run one burst unit on every busy CPU in parallel.
        for cpu_id, process in enumerate(self.running_slots):
            self.gantt.note_activity(
                self.current_time,
                process.process_id if process else None,
                cpu_id=cpu_id,
            )

        for cpu_id, process in enumerate(list(self.running_slots)):
            if process is None:
                continue
            process.remaining_burst = max(0, (process.remaining_burst or 0) - 1)
            self.busy_ticks += 1
            if self._scheduler.uses_time_quantum:
                self._quantum_remaining[cpu_id] -= 1

        self.current_time += 1

        for cpu_id, process in enumerate(list(self.running_slots)):
            if process is None:
                continue
            if process.remaining_burst == 0:
                process.mark_terminated(self.current_time)
                self.completed_processes.append(process)
                self.last_terminated.append(process.process_id)
                self._log(
                    self.current_time,
                    "terminate",
                    f"{process.process_id} terminated on CPU{cpu_id + 1}",
                    process.process_id,
                )
                self.running_slots[cpu_id] = None
                self._quantum_remaining[cpu_id] = 0
                continue

            if self._scheduler.uses_time_quantum and self._quantum_remaining[cpu_id] <= 0:
                process.mark_ready(self.current_time)
                self.ready_queue.enqueue(process)
                self._log(
                    self.current_time,
                    "preempt",
                    f"{process.process_id} quantum expired on CPU{cpu_id + 1} "
                    f"— returned to Ready Queue",
                    process.process_id,
                )
                self.running_slots[cpu_id] = None
                self._quantum_remaining[cpu_id] = 0

    def _check_completion(self) -> None:
        all_done = (
            len(self.processes) > 0
            and all(process.status is ProcessState.TERMINATED for process in self.processes)
            and all(slot is None for slot in self.running_slots)
            and len(self.ready_queue) == 0
        )
        if all_done and not self.is_complete:
            self.is_complete = True
            self.just_completed = True
            self.is_running = False
            self.gantt.finish(self.current_time)
            self._log(
                self.current_time,
                "complete",
                "All research processes finished",
            )

    def _log(
        self,
        time: int,
        kind: str,
        message: str,
        process_id: str | None = None,
    ) -> None:
        self.event_log.append(
            ExecutionEvent(
                time=time,
                kind=kind,
                message=message,
                process_id=process_id,
            )
        )

    def cpu_metrics(self) -> dict:
        elapsed = max(self.current_time, 1)
        capacity = elapsed * self.processor_count
        finished = [
            process
            for process in self.processes
            if process.status is ProcessState.TERMINATED
        ]
        average = lambda values: (sum(values) / len(values)) if values else 0.0
        return {
            "current_time": self.current_time,
            "processor_count": self.processor_count,
            "cpu_utilisation": round((self.busy_ticks / capacity) * 100, 2),
            "average_waiting_time": round(
                average([process.waiting_time for process in finished]), 2
            ),
            "average_turnaround_time": round(
                average([process.turnaround_time for process in finished]), 2
            ),
            "average_response_time": round(
                average(
                    [
                        process.response_time
                        for process in finished
                        if process.response_time is not None
                    ]
                ),
                2,
            ),
            "completed_count": len(finished),
            "total_processes": len(self.processes),
        }

    def snapshot(self) -> dict:
        waiting = [
            process.to_dict()
            for process in self.processes
            if process.status is ProcessState.WAITING
        ]
        cpus = []
        for cpu_id, process in enumerate(self.running_slots):
            cpus.append(
                {
                    "cpu_id": cpu_id + 1,
                    "status": "Busy" if process else "Idle",
                    "running": process.to_dict() if process else None,
                    "quantum_remaining": (
                        self._quantum_remaining[cpu_id]
                        if self._scheduler.uses_time_quantum and process
                        else None
                    ),
                }
            )
        primary = self.running_process
        return {
            "workload_name": self.workload_name,
            "scenario": self.scenario,
            "scheduling_policy": self._scheduler.policy.value,
            "time_quantum": self.time_quantum,
            "processor_count": self.processor_count,
            "current_time": self.current_time,
            "is_running": self.is_running,
            "is_complete": self.is_complete,
            "just_completed": self.just_completed,
            "last_admitted": list(self.last_admitted),
            "last_terminated": list(self.last_terminated),
            "cpu": {
                "status": "Busy" if primary else "Idle",
                "running": primary.to_dict() if primary else None,
                "quantum_remaining": (
                    next(
                        (
                            self._quantum_remaining[i]
                            for i, slot in enumerate(self.running_slots)
                            if slot is primary
                        ),
                        None,
                    )
                    if self._scheduler.uses_time_quantum and primary
                    else None
                ),
                "processors": cpus,
            },
            "ready_queue": self.ready_queue.process_ids(),
            "ready_queue_details": self.ready_queue.to_list(),
            "completed": [process.process_id for process in self.completed_processes],
            "waiting": waiting,
            "processes": [process.to_dict() for process in self.processes],
            "gantt": self.gantt.to_list(self.current_time),
            "metrics": self.cpu_metrics(),
            "event_log": [event.to_dict() for event in self.event_log[-40:]],
        }
