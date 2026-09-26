from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Disk:
    disk_id: int
    capacity_blocks: int = 32
    blocks: List[Optional[str]] = field(default_factory=list)
    failed: bool = False

    def __post_init__(self) -> None:
        if not self.blocks:
            self.blocks = [None] * self.capacity_blocks

    def to_dict(self) -> dict:
        return {
            "disk_id": self.disk_id,
            "failed": self.failed,
            "status": "FAILED" if self.failed else "ONLINE",
            "blocks": self.blocks,
            "used": sum(1 for b in self.blocks if b is not None),
            "capacity": self.capacity_blocks,
        }


class RAIDController:
    """Simulates RAID 0, 1, and 5 striping / mirroring / parity."""

    LEVELS = ("RAID 0", "RAID 1", "RAID 5")

    def __init__(self, level: str = "RAID 5", num_disks: int = 4, capacity: int = 24) -> None:
        self.level = level if level in self.LEVELS else "RAID 5"
        self.num_disks = max(2, num_disks)
        if self.level == "RAID 5":
            self.num_disks = max(3, self.num_disks)
        self.capacity = capacity
        self.disks: List[Disk] = [
            Disk(disk_id=i + 1, capacity_blocks=capacity) for i in range(self.num_disks)
        ]
        self.reads = 0
        self.writes = 0
        self.recoveries = 0
        self.last_event: Optional[dict] = None
        self.stored_pages: Dict[str, List[str]] = {}  # logical key -> stripe pieces

    def reset(self, level: Optional[str] = None, num_disks: Optional[int] = None) -> None:
        if level:
            self.level = level if level in self.LEVELS else self.level
        if num_disks:
            self.num_disks = max(2, num_disks)
            if self.level == "RAID 5":
                self.num_disks = max(3, self.num_disks)
        self.disks = [
            Disk(disk_id=i + 1, capacity_blocks=self.capacity) for i in range(self.num_disks)
        ]
        self.reads = 0
        self.writes = 0
        self.recoveries = 0
        self.last_event = None
        self.stored_pages = {}

    def _next_free_stripe_index(self) -> int:
        for i in range(self.capacity):
            if all(d.blocks[i] is None or d.failed for d in self.disks):
                # prefer truly empty row
                if all(d.blocks[i] is None for d in self.disks):
                    return i
        # fallback: first index
        return 0

    def write_page(self, pid: str, page: int) -> dict:
        key = f"{pid}:P{page}"
        data = f"{pid}-P{page}"
        idx = self._next_free_stripe_index()
        steps = [f"Write {data} using {self.level}"]

        if self.level == "RAID 0":
            # Stripe across disks
            pieces = []
            for i, disk in enumerate(self.disks):
                piece = f"{data}/S{i}"
                if not disk.failed:
                    disk.blocks[idx] = piece
                pieces.append(piece)
            self.stored_pages[key] = pieces
            steps.append(f"Striped across {self.num_disks} disks at stripe {idx}")

        elif self.level == "RAID 1":
            for disk in self.disks:
                if not disk.failed:
                    disk.blocks[idx] = data
            self.stored_pages[key] = [data]
            steps.append(f"Mirrored to all online disks at block {idx}")

        else:  # RAID 5
            # Rotate parity disk
            parity_disk = idx % self.num_disks
            data_disks = [d for i, d in enumerate(self.disks) if i != parity_disk]
            # Split into up to (n-1) pieces; for simplicity one data unit + parity
            primary = data_disks[0] if data_disks else self.disks[0]
            if not primary.failed:
                primary.blocks[idx] = data
            # Fake sibling data blocks for visualisation
            for j, d in enumerate(data_disks[1:], start=1):
                if not d.failed:
                    d.blocks[idx] = f"{data}/S{j}"
            parity_val = f"P({data})"
            if not self.disks[parity_disk].failed:
                self.disks[parity_disk].blocks[idx] = parity_val
            self.stored_pages[key] = [data, parity_val]
            steps.append(
                f"Data on disk(s), parity on Disk {parity_disk + 1} at stripe {idx}"
            )

        self.writes += 1
        event = {"type": "RAID_WRITE", "key": key, "stripe": idx, "steps": steps}
        self.last_event = event
        return event

    def read_page(self, pid: str, page: int) -> dict:
        key = f"{pid}:P{page}"
        self.reads += 1
        available = self.data_available()
        event = {
            "type": "RAID_READ",
            "key": key,
            "available": available,
            "steps": [
                f"Read {key} from {self.level}",
                "Data available" if available else "Data UNAVAILABLE due to disk failure",
            ],
        }
        self.last_event = event
        return event

    def fail_disk(self, disk_id: int) -> dict:
        target = None
        for d in self.disks:
            if d.disk_id == disk_id:
                target = d
                break
        if target is None:
            return {"type": "DISK_FAILURE", "error": "Disk not found"}

        target.failed = True
        available = self.data_available()
        recovery = self._recovery_plan(disk_id, available)
        event = {
            "type": "DISK_FAILURE",
            "failed_disk": disk_id,
            "data_available": available,
            "recovery": recovery,
            "message": "DISK FAILURE DETECTED",
        }
        self.last_event = event
        return event

    def recover_disk(self, disk_id: int) -> dict:
        target = next((d for d in self.disks if d.disk_id == disk_id), None)
        if not target:
            return {"error": "Disk not found"}
        if self.level == "RAID 0":
            return {
                "type": "RECOVERY",
                "success": False,
                "message": "RAID 0 cannot reconstruct lost data",
            }

        # Reconstruct from mirrors / parity (simulated)
        for i in range(self.capacity):
            if target.blocks[i] is None:
                donors = [d.blocks[i] for d in self.disks if not d.failed and d.blocks[i]]
                if donors:
                    # Prefer non-parity looking block
                    donor = next((b for b in donors if not str(b).startswith("P(")), donors[0])
                    if self.level == "RAID 5" and str(donor).startswith("P("):
                        continue
                    target.blocks[i] = donor if self.level == "RAID 1" else f"REBUILT:{donor}"
        target.failed = False
        self.recoveries += 1
        event = {
            "type": "RECOVERY",
            "success": True,
            "disk_id": disk_id,
            "message": "Disk rebuilt using redundancy/parity",
        }
        self.last_event = event
        return event

    def data_available(self) -> bool:
        failed = sum(1 for d in self.disks if d.failed)
        if self.level == "RAID 0":
            return failed == 0
        if self.level == "RAID 1":
            return failed < self.num_disks
        # RAID 5: tolerate 1 failure
        return failed <= 1

    def _recovery_plan(self, disk_id: int, available: bool) -> str:
        if self.level == "RAID 0":
            return "No redundancy. Lost stripe data cannot be reconstructed."
        if self.level == "RAID 1":
            return (
                f"Mirror copy available. Rebuild Disk {disk_id} from surviving mirror."
                if available
                else "All mirrors failed."
            )
        return (
            f"Reconstruct missing data on Disk {disk_id} using parity."
            if available
            else "Too many disks failed for RAID 5 recovery."
        )

    def comparison(self) -> List[dict]:
        n = self.num_disks
        return [
            {
                "level": "RAID 0",
                "read": "Excellent",
                "write": "Excellent",
                "efficiency": "100%",
                "fault_tolerance": "None",
                "disks_required": "2+",
                "capacity_factor": n,
            },
            {
                "level": "RAID 1",
                "read": "Good",
                "write": "Fair",
                "efficiency": f"{100 // n}%",
                "fault_tolerance": f"{n - 1} disks",
                "disks_required": "2+",
                "capacity_factor": 1,
            },
            {
                "level": "RAID 5",
                "read": "Good",
                "write": "Fair (parity)",
                "efficiency": f"{int((n - 1) / n * 100)}%",
                "fault_tolerance": "1 disk",
                "disks_required": "3+",
                "capacity_factor": n - 1,
            },
        ]

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "num_disks": self.num_disks,
            "disks": [d.to_dict() for d in self.disks],
            "reads": self.reads,
            "writes": self.writes,
            "recoveries": self.recoveries,
            "data_available": self.data_available(),
            "last_event": self.last_event,
            "comparison": self.comparison(),
            "storage_utilisation": round(
                sum(d.to_dict()["used"] for d in self.disks)
                / max(1, self.num_disks * self.capacity)
                * 100,
                2,
            ),
        }
