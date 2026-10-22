"""
Main memory paging for the research-centre HPC node.

Models Stallings-style paging: fixed-size pages mapped to frames,
with a per-process page table (frame, valid bit, dirty bit, location).

Relocation (Stallings): the CPU issues a logical address; the MMU maps it
to a physical address using the page table so a page can live in any free
frame without changing the program's logical addresses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil


@dataclass
class PageTableEntry:
    page_number: int
    frame_number: int | None = None
    valid: bool = False
    dirty: bool = False
    referenced: bool = False
    location: str = "Disk"  # RAM or Disk
    last_frame: int | None = None  # previous physical home (relocation history)

    def to_dict(self) -> dict:
        return {
            "page": self.page_number,
            "frame": self.frame_number,
            "valid_bit": 1 if self.valid else 0,
            "dirty_bit": 1 if self.dirty else 0,
            "referenced": self.referenced,
            "location": self.location,
            "last_frame": self.last_frame,
        }


@dataclass
class Frame:
    frame_number: int
    process_id: str | None = None
    page_number: int | None = None
    load_time: int = 0
    last_used: int = 0

    @property
    def free(self) -> bool:
        return self.process_id is None

    def to_dict(self) -> dict:
        return {
            "frame": self.frame_number,
            "process_id": self.process_id,
            "page_number": self.page_number,
            "label": (
                "FREE"
                if self.free
                else f"{self.process_id}-pg{self.page_number}"
            ),
            "load_time": self.load_time,
            "last_used": self.last_used,
        }


@dataclass
class MemoryManager:
    """
    Physical RAM divided into frames; processes divided into pages.

    Page size (logical) and frame size (physical) are configured separately.
    Hardware normally uses equal sizes; the simulator keeps both so you can
    set each explicitly. RAM = frame_count × frame_size.
    """

    ram_size_kb: int = 32
    page_size_kb: int = 4
    frame_size_kb: int = 4
    current_time: int = 0
    frames: list[Frame] = field(default_factory=list)
    page_tables: dict[str, list[PageTableEntry]] = field(default_factory=dict)
    process_sizes_kb: dict[str, int] = field(default_factory=dict)

    page_faults: int = 0
    page_hits: int = 0
    pages_transferred: int = 0
    page_replacements: int = 0
    relocations: int = 0
    fault_events: list[dict] = field(default_factory=list)
    last_translation: dict | None = None

    def __post_init__(self) -> None:
        self.reconfigure(self.ram_size_kb, self.page_size_kb, self.frame_size_kb)

    @property
    def frame_count(self) -> int:
        return max(1, self.ram_size_kb // self.frame_size_kb)

    def reconfigure(
        self,
        ram_size_kb: int,
        page_size_kb: int,
        frame_size_kb: int | None = None,
        frame_count: int | None = None,
    ) -> None:
        self.page_size_kb = max(1, page_size_kb)
        self.frame_size_kb = max(1, frame_size_kb if frame_size_kb is not None else page_size_kb)
        if frame_count is not None and frame_count >= 1:
            self.ram_size_kb = frame_count * self.frame_size_kb
        else:
            self.ram_size_kb = max(self.frame_size_kb, ram_size_kb)
        self.frames = [Frame(frame_number=i) for i in range(self.frame_count)]
        self.page_tables.clear()
        self.process_sizes_kb.clear()
        self.page_faults = 0
        self.page_hits = 0
        self.pages_transferred = 0
        self.page_replacements = 0
        self.relocations = 0
        self.fault_events.clear()
        self.last_translation = None
        self.current_time = 0

    def pages_required(self, size_kb: int) -> int:
        return max(1, ceil(size_kb / self.page_size_kb))

    def relocate(self, page_number: int, frame_number: int, offset_kb: int = 0) -> dict:
        """
        Stallings relocation for paging:
          logical  = page_number × page_size + offset
          physical = frame_number × frame_size + offset
        Page size and frame size are separate settings (normally equal).
        """
        max_off = max(0, min(self.page_size_kb, self.frame_size_kb) - 1)
        offset_kb = max(0, min(offset_kb, max_off))
        logical = page_number * self.page_size_kb + offset_kb
        physical = frame_number * self.frame_size_kb + offset_kb
        return {
            "principle": "relocation",
            "scheme": "Paging",
            "logical_address_kb": logical,
            "physical_address_kb": physical,
            "page": page_number,
            "frame": frame_number,
            "offset_kb": offset_kb,
            "page_size_kb": self.page_size_kb,
            "frame_size_kb": self.frame_size_kb,
            "formula": (
                f"logical={page_number}*{self.page_size_kb}+{offset_kb}={logical}KB -> "
                f"physical={frame_number}*{self.frame_size_kb}+{offset_kb}={physical}KB"
            ),
        }

    def register_process(self, process_id: str, size_kb: int) -> list[PageTableEntry]:
        page_count = self.pages_required(size_kb)
        table = [PageTableEntry(page_number=i) for i in range(page_count)]
        self.page_tables[process_id] = table
        self.process_sizes_kb[process_id] = size_kb
        return table

    def free_frame_list(self) -> list[int]:
        return [frame.frame_number for frame in self.frames if frame.free]

    def occupied_frame_list(self) -> list[dict]:
        return [frame.to_dict() for frame in self.frames if not frame.free]

    def allocate_initial_pages(
        self,
        process_id: str,
        max_pages: int | None = None,
    ) -> list[dict]:
        """
        Prepaging: load as many of the process's pages as free frames allow.
        Skips pages already resident.
        """
        if process_id not in self.page_tables:
            raise KeyError(process_id)
        table = self.page_tables[process_id]
        limit = len(table) if max_pages is None else min(max_pages, len(table))
        actions = []
        for entry in table[:limit]:
            if entry.valid:
                continue
            free = self.free_frame_list()
            if not free:
                break
            self.current_time += 1
            frame_no = free[0]
            self._load_page(process_id, entry.page_number, frame_no, dirty=False)
            self.pages_transferred += 1
            actions.append(
                {
                    "process_id": process_id,
                    "page": entry.page_number,
                    "frame": frame_no,
                }
            )
        if actions:
            first = actions[0]
            last = actions[-1]
            self.last_translation = self.relocate(last["page"], last["frame"])
            self.last_translation["prepaging"] = True
            self.last_translation["pages_loaded"] = len(actions)
        return actions

    def access_page(
        self,
        process_id: str,
        page_number: int,
        write: bool = False,
        replacement_algo: str = "FIFO",
        future_refs: list[tuple[str, int]] | None = None,
    ) -> dict:
        """
        CPU references a logical page.
        Hit → update reference/dirty bits.
        Miss → PAGE FAULT, possibly replace a victim, load from secondary storage.
        """
        table = self.page_tables[process_id]
        if page_number < 0 or page_number >= len(table):
            raise ValueError(f"Page {page_number} out of range for {process_id}")

        entry = table[page_number]
        self.current_time += 1
        logical_kb = page_number * self.page_size_kb

        if entry.valid and entry.frame_number is not None:
            self.page_hits += 1
            entry.referenced = True
            if write:
                entry.dirty = True
            self.frames[entry.frame_number].last_used = self.current_time
            translation = self.relocate(page_number, entry.frame_number)
            self.last_translation = translation
            return {
                "result": "HIT",
                "process_id": process_id,
                "page": page_number,
                "frame": entry.frame_number,
                "relocation": translation,
                "message": (
                    f"Page hit + relocate: {process_id} logical pg{page_number} "
                    f"({logical_kb}KB) -> frame {entry.frame_number} "
                    f"(physical {translation['physical_address_kb']}KB)"
                ),
                "steps": [
                    f"Relocation: {translation['formula']}",
                ],
            }

        # PAGE FAULT — may place the logical page in a new physical frame (relocation)
        self.page_faults += 1
        previous_frame = entry.last_frame
        steps = [
            f"PAGE FAULT! Logical {process_id}:pg{page_number} (addr {logical_kb}KB)",
            "1. Locate pg on secondary storage",
        ]
        free = self.free_frame_list()
        victim = None
        if free:
            frame_no = free[0]
            steps.append(f"2. Free frame found: Frame {frame_no}")
        else:
            victim = self._select_victim(replacement_algo, future_refs or [])
            frame_no = victim["frame"]
            steps.append(
                f"2. No free frame — victim {victim['process_id']} "
                f"pg{victim['page']} selected ({replacement_algo})"
            )
            steps.append("3. Move victim pg to secondary storage")
            self._evict(victim["process_id"], victim["page"])
            self.page_replacements += 1

        relocated = previous_frame is not None and previous_frame != frame_no
        if relocated:
            self.relocations += 1
            steps.append(
                f"4. Relocate logical pg into Frame {frame_no} "
                f"(was previously in Frame {previous_frame})"
            )
        else:
            steps.append(f"4. Load logical pg into Frame {frame_no} (dynamic relocation)")
        self._load_page(process_id, page_number, frame_no, dirty=write)
        self.pages_transferred += 1
        translation = self.relocate(page_number, frame_no)
        self.last_translation = translation
        steps.append(f"5. Update page table — {translation['formula']}")
        steps.append("6. Continue process execution at physical address")

        event = {
            "result": "FAULT",
            "process_id": process_id,
            "page": page_number,
            "frame": frame_no,
            "victim": victim,
            "algorithm": replacement_algo,
            "relocated": relocated,
            "previous_frame": previous_frame,
            "relocation": translation,
            "message": (
                f"PAGE FAULT + relocate: {process_id} pg{page_number} -> frame {frame_no}"
                + (f" (was frame {previous_frame})" if relocated else "")
            ),
            "steps": steps,
            "time": self.current_time,
        }
        self.fault_events.append(event)
        return event

    def _load_page(
        self,
        process_id: str,
        page_number: int,
        frame_no: int,
        dirty: bool,
    ) -> None:
        frame = self.frames[frame_no]
        frame.process_id = process_id
        frame.page_number = page_number
        frame.load_time = self.current_time
        frame.last_used = self.current_time
        entry = self.page_tables[process_id][page_number]
        entry.frame_number = frame_no
        entry.last_frame = frame_no
        entry.valid = True
        entry.dirty = dirty
        entry.referenced = True
        entry.location = "RAM"

    def _evict(self, process_id: str, page_number: int) -> None:
        entry = self.page_tables[process_id][page_number]
        if entry.frame_number is not None:
            entry.last_frame = entry.frame_number
            frame = self.frames[entry.frame_number]
            frame.process_id = None
            frame.page_number = None
        entry.frame_number = None
        entry.valid = False
        entry.referenced = False
        entry.dirty = False
        entry.location = "Disk"

    def release_process(self, process_id: str) -> list[dict]:
        """Free every resident frame when a process terminates (address-space teardown)."""
        table = self.page_tables.get(process_id)
        if not table:
            return []
        actions: list[dict] = []
        for entry in list(table):
            if not entry.valid or entry.frame_number is None:
                continue
            frame_no = entry.frame_number
            page_no = entry.page_number
            self._evict(process_id, page_no)
            actions.append(
                {
                    "process_id": process_id,
                    "page": page_no,
                    "frame": frame_no,
                    "action": "OUT",
                }
            )
        return actions

    def _select_victim(
        self,
        algorithm: str,
        future_refs: list[tuple[str, int]],
    ) -> dict:
        occupied = [frame for frame in self.frames if not frame.free]
        if not occupied:
            raise RuntimeError("No occupied frame to replace")

        algo = algorithm.strip().upper()
        if algo == "LRU":
            chosen = min(occupied, key=lambda frame: frame.last_used)
        elif algo in {"OPT", "OPTIMAL"}:
            chosen = self._optimal_victim(occupied, future_refs)
        else:  # FIFO default
            chosen = min(occupied, key=lambda frame: frame.load_time)

        return {
            "frame": chosen.frame_number,
            "process_id": chosen.process_id,
            "page": chosen.page_number,
        }

    def _optimal_victim(
        self,
        occupied: list[Frame],
        future_refs: list[tuple[str, int]],
    ) -> Frame:
        def next_use(frame: Frame) -> int:
            for index, (pid, page) in enumerate(future_refs):
                if pid == frame.process_id and page == frame.page_number:
                    return index
            return 10**9

        return max(occupied, key=next_use)

    def internal_fragmentation_kb(self) -> int:
        waste = 0
        for size in self.process_sizes_kb.values():
            rem = size % self.page_size_kb
            if rem:
                waste += self.page_size_kb - rem
        return waste

    def metrics(self) -> dict:
        refs = self.page_hits + self.page_faults
        occupied = sum(1 for frame in self.frames if not frame.free)
        internal = self.internal_fragmentation_kb()
        return {
            "scheme": "Paging",
            "page_faults": self.page_faults,
            "page_hits": self.page_hits,
            "page_fault_rate": round((self.page_faults / refs) * 100, 2) if refs else 0.0,
            "page_hit_rate": round((self.page_hits / refs) * 100, 2) if refs else 0.0,
            "page_replacements": self.page_replacements,
            "pages_transferred": self.pages_transferred,
            "memory_utilisation": round((occupied / len(self.frames)) * 100, 2),
            "frames_total": len(self.frames),
            "frames_free": len(self.free_frame_list()),
            "ram_size_kb": self.ram_size_kb,
            "ram_used_kb": occupied * self.frame_size_kb,
            "ram_free_kb": len(self.free_frame_list()) * self.frame_size_kb,
            "pages_in_ram": occupied,
            "pages_on_disk": sum(
                1
                for table in self.page_tables.values()
                for entry in table
                if not entry.valid
            ),
            "internal_fragmentation_kb": internal,
            "external_fragmentation_kb": 0,
            "external_fragmentation_pct": 0.0,
            "allocation_failures": 0,
            "free_holes": 0,
            "relocations": self.relocations,
        }

    def snapshot(self) -> dict:
        page_tables: dict[str, list[dict]] = {}
        for pid, table in self.page_tables.items():
            rows = []
            for entry in table:
                row = entry.to_dict()
                row["logical_start_kb"] = entry.page_number * self.page_size_kb
                show_frame = (
                    entry.frame_number
                    if entry.valid and entry.frame_number is not None
                    else entry.last_frame
                )
                row["display_frame"] = show_frame
                row["physical_start_kb"] = (
                    show_frame * self.frame_size_kb if show_frame is not None else None
                )
                rows.append(row)
            page_tables[pid] = rows
        return {
            "scheme": "Paging",
            "ram_size_kb": self.ram_size_kb,
            "page_size_kb": self.page_size_kb,
            "frame_size_kb": self.frame_size_kb,
            "frame_count": self.frame_count,
            "frames": [frame.to_dict() for frame in self.frames],
            "regions": [],
            "free_frames": self.free_frame_list(),
            "occupied_frames": self.occupied_frame_list(),
            "page_tables": page_tables,
            "segment_tables": {},
            "metrics": self.metrics(),
            "recent_faults": self.fault_events[-10:],
            "last_translation": self.last_translation,
        }
