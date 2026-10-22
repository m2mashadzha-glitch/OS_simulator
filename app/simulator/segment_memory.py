"""
Segmentation memory manager (Stallings-style, for comparison with paging).

Each process is split into variable-sized logical segments (Code, Data, Stack).
Segments occupy contiguous regions of RAM (first-fit). External fragmentation
is the main performance cost relative to paging.
"""

from __future__ import annotations

from dataclasses import dataclass, field


SEGMENT_NAMES = ("Code", "Data", "Stack")


@dataclass
class SegmentEntry:
    segment_id: int
    name: str
    size_kb: int
    base: int | None = None  # physical start in RAM when resident
    limit: int | None = None  # same as size when resident
    valid: bool = False
    location: str = "Disk"
    last_base: int | None = None  # previous physical base (relocation history)

    def to_dict(self) -> dict:
        return {
            "segment": self.segment_id,
            "name": self.name,
            "size_kb": self.size_kb,
            "base": self.base,
            "limit": self.limit if self.valid else self.size_kb,
            "valid_bit": 1 if self.valid else 0,
            "location": self.location,
            "last_base": self.last_base,
        }


@dataclass
class MemoryRegion:
    start: int
    size: int
    free: bool = True
    process_id: str | None = None
    segment_id: int | None = None
    label: str = "FREE"

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "size": self.size,
            "free": self.free,
            "process_id": self.process_id,
            "segment_id": self.segment_id,
            "label": self.label,
        }


@dataclass
class SegmentMemoryManager:
    """Contiguous RAM allocation with a per-process segment table."""

    ram_size_kb: int = 32
    current_time: int = 0
    regions: list[MemoryRegion] = field(default_factory=list)
    segment_tables: dict[str, list[SegmentEntry]] = field(default_factory=dict)
    process_sizes_kb: dict[str, int] = field(default_factory=dict)

    segment_faults: int = 0
    segment_hits: int = 0
    segment_replacements: int = 0
    segments_transferred: int = 0
    allocation_failures: int = 0
    relocations: int = 0
    fault_events: list[dict] = field(default_factory=list)
    last_translation: dict | None = None

    def __post_init__(self) -> None:
        self.reconfigure(self.ram_size_kb)

    def reconfigure(self, ram_size_kb: int) -> None:
        self.ram_size_kb = max(1, ram_size_kb)
        self.regions = [MemoryRegion(start=0, size=self.ram_size_kb, free=True)]
        self.segment_tables.clear()
        self.process_sizes_kb.clear()
        self.segment_faults = 0
        self.segment_hits = 0
        self.segment_replacements = 0
        self.segments_transferred = 0
        self.allocation_failures = 0
        self.relocations = 0
        self.fault_events.clear()
        self.last_translation = None
        self.current_time = 0

    def relocate(self, base_kb: int, offset_kb: int, limit_kb: int) -> dict:
        """
        Stallings relocation for segmentation:
          physical = base + offset   (if offset < limit)
        Base is the relocation register for the segment.
        """
        offset_kb = max(0, offset_kb)
        ok = offset_kb < limit_kb
        physical = base_kb + offset_kb if ok else None
        return {
            "principle": "relocation",
            "scheme": "Segmentation",
            "base_kb": base_kb,
            "limit_kb": limit_kb,
            "offset_kb": offset_kb,
            "logical_address_kb": offset_kb,
            "physical_address_kb": physical,
            "in_bounds": ok,
            "formula": (
                f"physical = base({base_kb}) + offset({offset_kb}) = {physical}KB"
                if ok
                else f"offset {offset_kb} >= limit {limit_kb} — addressing error"
            ),
        }

    @staticmethod
    def split_process(size_kb: int) -> list[tuple[str, int]]:
        size_kb = max(3, size_kb)
        code = max(1, int(size_kb * 0.4))
        data = max(1, int(size_kb * 0.4))
        stack = max(1, size_kb - code - data)
        return [("Code", code), ("Data", data), ("Stack", stack)]

    def register_process(self, process_id: str, size_kb: int) -> list[SegmentEntry]:
        parts = self.split_process(size_kb)
        table = [
            SegmentEntry(segment_id=i, name=name, size_kb=seg_size)
            for i, (name, seg_size) in enumerate(parts)
        ]
        self.segment_tables[process_id] = table
        self.process_sizes_kb[process_id] = size_kb
        return table

    def _merge_free(self) -> None:
        merged: list[MemoryRegion] = []
        for region in sorted(self.regions, key=lambda item: item.start):
            if merged and merged[-1].free and region.free:
                merged[-1].size += region.size
            else:
                merged.append(
                    MemoryRegion(
                        start=region.start,
                        size=region.size,
                        free=region.free,
                        process_id=region.process_id,
                        segment_id=region.segment_id,
                        label=region.label,
                    )
                )
        self.regions = merged

    def _free_holes(self) -> list[MemoryRegion]:
        return [region for region in self.regions if region.free]

    def _first_fit(self, size_kb: int) -> int | None:
        for index, region in enumerate(self.regions):
            if region.free and region.size >= size_kb:
                return index
        return None

    def _place(
        self,
        hole_index: int,
        process_id: str,
        segment: SegmentEntry,
    ) -> int:
        hole = self.regions[hole_index]
        base = hole.start
        used = MemoryRegion(
            start=base,
            size=segment.size_kb,
            free=False,
            process_id=process_id,
            segment_id=segment.segment_id,
            label=f"{process_id}:{segment.name}",
        )
        leftover = hole.size - segment.size_kb
        new_regions = self.regions[:hole_index] + [used]
        if leftover > 0:
            new_regions.append(
                MemoryRegion(start=base + segment.size_kb, size=leftover, free=True)
            )
        new_regions.extend(self.regions[hole_index + 1 :])
        self.regions = new_regions
        self._merge_free()
        segment.base = base
        segment.limit = segment.size_kb
        segment.valid = True
        segment.location = "RAM"
        return base

    def _evict_segment(self, process_id: str, segment_id: int) -> None:
        table = self.segment_tables[process_id]
        segment = table[segment_id]
        if not segment.valid or segment.base is None:
            return
        segment.last_base = segment.base
        self.regions = [
            MemoryRegion(start=region.start, size=region.size, free=True)
            if (
                not region.free
                and region.process_id == process_id
                and region.segment_id == segment_id
            )
            else region
            for region in self.regions
        ]
        self._merge_free()
        segment.base = None
        segment.limit = None
        segment.valid = False
        segment.location = "Disk"
        self.segment_replacements += 1

    def release_process(self, process_id: str) -> list[dict]:
        """Free all resident segments when a process terminates."""
        table = self.segment_tables.get(process_id)
        if not table:
            return []
        actions: list[dict] = []
        for entry in list(table):
            if not entry.valid:
                continue
            base = entry.base
            name = entry.name
            self._evict_segment(process_id, entry.segment_id)
            # Eviction increments replacements; teardown is not a replacement.
            self.segment_replacements = max(0, self.segment_replacements - 1)
            actions.append(
                {
                    "process_id": process_id,
                    "name": name,
                    "base": base,
                    "action": "OUT",
                }
            )
        return actions

    def _select_victim(self) -> tuple[str, int] | None:
        residents: list[tuple[str, int, int, int]] = []
        for pid, table in self.segment_tables.items():
            for entry in table:
                if entry.valid:
                    residents.append((pid, entry.segment_id, entry.size_kb, entry.segment_id))
        if not residents:
            return None
        # Evict largest resident segment (exposes external fragmentation cost).
        pid, seg_id, _, _ = max(residents, key=lambda item: item[2])
        return pid, seg_id

    def access_segment(self, process_id: str, segment_id: int) -> dict:
        table = self.segment_tables[process_id]
        if segment_id < 0 or segment_id >= len(table):
            raise ValueError(f"Segment {segment_id} out of range for {process_id}")

        segment = table[segment_id]
        self.current_time += 1

        if segment.valid and segment.base is not None:
            self.segment_hits += 1
            translation = self.relocate(segment.base, 0, segment.size_kb)
            self.last_translation = translation
            return {
                "result": "HIT",
                "scheme": "Segmentation",
                "process_id": process_id,
                "segment": segment_id,
                "name": segment.name,
                "base": segment.base,
                "relocation": translation,
                "message": (
                    f"Segment hit + relocate: {process_id}:{segment.name} "
                    f"base={segment.base}KB -> {translation['formula']}"
                ),
                "steps": [f"Relocation: {translation['formula']}"],
            }

        self.segment_faults += 1
        steps = [
            f"SEGMENT FAULT! Requested {process_id}:{segment.name} ({segment.size_kb}KB)",
            "1. Locate segment on secondary storage",
            "2. Search RAM for a contiguous hole (first-fit)",
        ]
        victim = None
        hole_index = self._first_fit(segment.size_kb)
        if hole_index is None:
            steps.append("3. No hole large enough — external fragmentation / full RAM")
            choice = self._select_victim()
            if choice is None:
                self.allocation_failures += 1
                event = {
                    "result": "FAULT",
                    "scheme": "Segmentation",
                    "process_id": process_id,
                    "segment": segment_id,
                    "name": segment.name,
                    "message": f"SEGMENT FAULT FAILED: no space for {process_id}:{segment.name}",
                    "steps": steps + ["4. Allocation failed"],
                    "time": self.current_time,
                }
                self.fault_events.append(event)
                return event
            v_pid, v_seg = choice
            v_name = self.segment_tables[v_pid][v_seg].name
            steps.append(f"4. Evict victim {v_pid}:{v_name} to secondary storage")
            self._evict_segment(v_pid, v_seg)
            victim = {"process_id": v_pid, "segment": v_seg, "name": v_name}
            hole_index = self._first_fit(segment.size_kb)
            if hole_index is None:
                self.allocation_failures += 1
                event = {
                    "result": "FAULT",
                    "scheme": "Segmentation",
                    "process_id": process_id,
                    "segment": segment_id,
                    "name": segment.name,
                    "victim": victim,
                    "message": f"SEGMENT FAULT FAILED after eviction for {process_id}:{segment.name}",
                    "steps": steps + ["5. Still no contiguous hole — allocation failed"],
                    "time": self.current_time,
                }
                self.fault_events.append(event)
                return event
        else:
            steps.append(f"3. Hole found at {self.regions[hole_index].start}KB")

        previous_base = segment.last_base
        base = self._place(hole_index, process_id, segment)
        segment.last_base = base
        self.segments_transferred += 1
        relocated = previous_base is not None and previous_base != base
        if relocated:
            self.relocations += 1
            steps.append(
                f"5. Relocate segment to base {base}KB "
                f"(was previously at {previous_base}KB; limit {segment.size_kb}KB)"
            )
        else:
            steps.append(
                f"5. Load segment at base {base}KB "
                f"(limit {segment.size_kb}KB) — physical = base + offset"
            )
        translation = self.relocate(base, 0, segment.size_kb)
        self.last_translation = translation
        steps.append(f"6. Update segment table — {translation['formula']}")
        steps.append("7. Continue process execution at physical address")

        event = {
            "result": "FAULT",
            "scheme": "Segmentation",
            "process_id": process_id,
            "segment": segment_id,
            "name": segment.name,
            "base": base,
            "victim": victim,
            "relocated": relocated,
            "previous_base": previous_base,
            "relocation": translation,
            "message": (
                f"SEGMENT FAULT + relocate: {process_id}:{segment.name} -> base {base}KB"
                + (f" (was {previous_base}KB)" if relocated else "")
            ),
            "steps": steps,
            "time": self.current_time,
        }
        self.fault_events.append(event)
        return event

    def external_fragmentation_kb(self) -> int:
        holes = self._free_holes()
        if not holes:
            return 0
        total_free = sum(hole.size for hole in holes)
        largest = max(hole.size for hole in holes)
        return max(0, total_free - largest)

    def metrics(self) -> dict:
        refs = self.segment_hits + self.segment_faults
        used = sum(region.size for region in self.regions if not region.free)
        holes = self._free_holes()
        total_free = sum(hole.size for hole in holes)
        largest = max((hole.size for hole in holes), default=0)
        ext = self.external_fragmentation_kb()
        return {
            "scheme": "Segmentation",
            "segment_faults": self.segment_faults,
            "segment_hits": self.segment_hits,
            "fault_rate": round((self.segment_faults / refs) * 100, 2) if refs else 0.0,
            "hit_rate": round((self.segment_hits / refs) * 100, 2) if refs else 0.0,
            "segment_replacements": self.segment_replacements,
            "segments_transferred": self.segments_transferred,
            "allocation_failures": self.allocation_failures,
            "memory_utilisation": round((used / self.ram_size_kb) * 100, 2),
            "external_fragmentation_kb": ext,
            "external_fragmentation_pct": (
                round((ext / total_free) * 100, 2) if total_free else 0.0
            ),
            "internal_fragmentation_kb": 0,
            "free_holes": len(holes),
            "largest_hole_kb": largest,
            "ram_size_kb": self.ram_size_kb,
            "ram_used_kb": used,
            "ram_free_kb": total_free,
            "frames_total": 0,
            # Aliases so dashboard can share keys with paging where useful
            "page_faults": self.segment_faults,
            "page_hits": self.segment_hits,
            "page_fault_rate": round((self.segment_faults / refs) * 100, 2) if refs else 0.0,
            "page_hit_rate": round((self.segment_hits / refs) * 100, 2) if refs else 0.0,
            "page_replacements": self.segment_replacements,
            "pages_transferred": self.segments_transferred,
            "pages_in_ram": sum(
                1
                for table in self.segment_tables.values()
                for entry in table
                if entry.valid
            ),
            "pages_on_disk": sum(
                1
                for table in self.segment_tables.values()
                for entry in table
                if not entry.valid
            ),
            "frames_total": 0,
            "frames_free": 0,
            "relocations": self.relocations,
        }

    def snapshot(self) -> dict:
        return {
            "scheme": "Segmentation",
            "ram_size_kb": self.ram_size_kb,
            "page_size_kb": None,
            "frame_count": 0,
            "regions": [region.to_dict() for region in self.regions],
            "frames": [],
            "free_frames": [],
            "occupied_frames": [],
            "segment_tables": {
                pid: [entry.to_dict() for entry in table]
                for pid, table in self.segment_tables.items()
            },
            "page_tables": {},
            "metrics": self.metrics(),
            "recent_faults": self.fault_events[-10:],
            "last_translation": self.last_translation,
        }
