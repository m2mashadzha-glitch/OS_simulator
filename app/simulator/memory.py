from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class PageTableEntry:
    page: int
    frame: Optional[int] = None
    valid: bool = False
    dirty: bool = False
    location: str = "Disk"  # RAM | Disk
    last_used: int = 0
    load_time: int = 0

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "frame": self.frame,
            "valid": self.valid,
            "dirty": self.dirty,
            "location": self.location,
            "last_used": self.last_used,
            "load_time": self.load_time,
        }


@dataclass
class MemoryManager:
    ram_size_kb: int = 32
    page_size_kb: int = 4
    virtual_size_kb: int = 64
    replacement: str = "FIFO"  # FIFO | LRU | Optimal
    frames: Dict[int, Optional[Tuple[str, int]]] = field(default_factory=dict)
    # frame -> (pid, page) or None
    page_tables: Dict[str, Dict[int, PageTableEntry]] = field(default_factory=dict)
    fifo_order: List[Tuple[str, int]] = field(default_factory=list)
    future_refs: List[int] = field(default_factory=list)
    future_index: int = 0
    page_faults: int = 0
    page_hits: int = 0
    replacements: int = 0
    transfers: int = 0
    last_event: Optional[dict] = None

    def __post_init__(self) -> None:
        self.reconfigure(
            self.ram_size_kb,
            self.page_size_kb,
            self.virtual_size_kb,
            self.replacement,
        )

    @property
    def num_frames(self) -> int:
        return max(1, self.ram_size_kb // self.page_size_kb)

    @property
    def num_virtual_pages(self) -> int:
        return max(1, self.virtual_size_kb // self.page_size_kb)

    def reconfigure(
        self,
        ram_size_kb: int,
        page_size_kb: int,
        virtual_size_kb: int,
        replacement: str = "FIFO",
    ) -> None:
        self.ram_size_kb = max(page_size_kb, ram_size_kb)
        self.page_size_kb = max(1, page_size_kb)
        self.virtual_size_kb = max(self.ram_size_kb, virtual_size_kb)
        self.replacement = replacement if replacement in ("FIFO", "LRU", "Optimal") else "FIFO"
        self.frames = {i: None for i in range(self.num_frames)}
        self.page_tables = {}
        self.fifo_order = []
        self.page_faults = 0
        self.page_hits = 0
        self.replacements = 0
        self.transfers = 0
        self.last_event = None
        self.future_index = 0

    def ensure_process(self, pid: str, num_pages: int) -> None:
        if pid in self.page_tables:
            return
        pages = max(num_pages, 1)
        # Cap by virtual address space for demo clarity
        pages = min(pages, self.num_virtual_pages)
        self.page_tables[pid] = {
            p: PageTableEntry(page=p) for p in range(pages)
        }

    def free_frame_list(self) -> List[int]:
        return [i for i, occ in self.frames.items() if occ is None]

    def occupied_frames(self) -> Dict[int, dict]:
        out = {}
        for i, occ in self.frames.items():
            if occ is None:
                out[i] = {"free": True}
            else:
                pid, page = occ
                out[i] = {"free": False, "pid": pid, "page": page}
        return out

    def _find_victim(self, time: int) -> Tuple[str, int]:
        occupied = [occ for occ in self.frames.values() if occ is not None]
        if not occupied:
            raise RuntimeError("No victim available")

        if self.replacement == "FIFO":
            while self.fifo_order:
                candidate = self.fifo_order[0]
                if candidate in occupied:
                    return candidate
                self.fifo_order.pop(0)
            return occupied[0]

        if self.replacement == "LRU":
            best = None
            best_time = float("inf")
            for pid, page in occupied:
                entry = self.page_tables[pid][page]
                if entry.last_used < best_time:
                    best_time = entry.last_used
                    best = (pid, page)
            return best or occupied[0]

        # Optimal: replace page not used for longest in future
        future = self.future_refs[self.future_index :]
        farthest = -1
        victim = occupied[0]
        for pid, page in occupied:
            try:
                dist = future.index(page)
            except ValueError:
                dist = 10**9
            if dist > farthest:
                farthest = dist
                victim = (pid, page)
        return victim

    def access(self, pid: str, page: int, time: int) -> dict:
        self.ensure_process(pid, page + 1)
        table = self.page_tables[pid]
        if page not in table:
            # Expand table if reference is within virtual space
            if page >= self.num_virtual_pages:
                page = page % self.num_virtual_pages
            table[page] = PageTableEntry(page=page)

        entry = table[page]
        if entry.valid and entry.frame is not None:
            self.page_hits += 1
            entry.last_used = time
            self.future_index += 1
            event = {
                "type": "PAGE_HIT",
                "pid": pid,
                "page": page,
                "frame": entry.frame,
                "steps": [f"Page {page} of {pid} found in Frame {entry.frame}"],
            }
            self.last_event = event
            return event

        # Page fault
        self.page_faults += 1
        steps = [
            f"PAGE FAULT! {pid} requested page {page}",
            "Locate page on secondary storage",
        ]
        free = self.free_frame_list()
        victim_info = None
        if free:
            frame = free[0]
            steps.append(f"Free frame found: Frame {frame}")
        else:
            v_pid, v_page = self._find_victim(time)
            v_entry = self.page_tables[v_pid][v_page]
            frame = v_entry.frame
            assert frame is not None
            steps.append(f"Select victim page: {v_pid} page {v_page} (Frame {frame})")
            steps.append("Move victim page to secondary storage")
            v_entry.valid = False
            v_entry.frame = None
            v_entry.location = "Disk"
            self.frames[frame] = None
            if (v_pid, v_page) in self.fifo_order:
                self.fifo_order.remove((v_pid, v_page))
            self.replacements += 1
            self.transfers += 1
            victim_info = {"pid": v_pid, "page": v_page, "frame": frame}

        steps.append(f"Load requested page {page} into Frame {frame}")
        steps.append("Update page table")
        steps.append("Continue process execution")

        entry.valid = True
        entry.frame = frame
        entry.location = "RAM"
        entry.last_used = time
        entry.load_time = time
        self.frames[frame] = (pid, page)
        self.fifo_order.append((pid, page))
        self.transfers += 1
        self.future_index += 1

        event = {
            "type": "PAGE_FAULT",
            "pid": pid,
            "page": page,
            "frame": frame,
            "victim": victim_info,
            "steps": steps,
        }
        self.last_event = event
        return event

    def fault_rate(self) -> float:
        total = self.page_faults + self.page_hits
        return (self.page_faults / total * 100) if total else 0.0

    def hit_rate(self) -> float:
        total = self.page_faults + self.page_hits
        return (self.page_hits / total * 100) if total else 0.0

    def to_dict(self) -> dict:
        tables = {
            pid: [e.to_dict() for e in sorted(entries.values(), key=lambda x: x.page)]
            for pid, entries in self.page_tables.items()
        }
        return {
            "ram_size_kb": self.ram_size_kb,
            "page_size_kb": self.page_size_kb,
            "virtual_size_kb": self.virtual_size_kb,
            "num_frames": self.num_frames,
            "num_virtual_pages": self.num_virtual_pages,
            "replacement": self.replacement,
            "frames": self.occupied_frames(),
            "free_frames": self.free_frame_list(),
            "page_tables": tables,
            "page_faults": self.page_faults,
            "page_hits": self.page_hits,
            "fault_rate": round(self.fault_rate(), 2),
            "hit_rate": round(self.hit_rate(), 2),
            "replacements": self.replacements,
            "transfers": self.transfers,
            "last_event": self.last_event,
            "memory_utilisation": round(
                (self.num_frames - len(self.free_frame_list())) / self.num_frames * 100, 2
            ),
        }
