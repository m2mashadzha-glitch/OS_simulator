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
    """Simulates RAID 0, 1, 5, 6, and 10 (1+0)."""

    LEVELS = ("RAID 0", "RAID 1", "RAID 5", "RAID 6", "RAID 10")

    def __init__(self, level: str = "RAID 5", num_disks: int = 4, capacity: int = 24) -> None:
        self.capacity = capacity
        self.reads = 0
        self.writes = 0
        self.recoveries = 0
        self.last_event: Optional[dict] = None
        self.stored_pages: Dict[str, List[str]] = {}
        self.level = "RAID 5"
        self.num_disks = 4
        self.disks: List[Disk] = []
        self.reset(level=level, num_disks=num_disks)

    def _min_disks(self, level: str) -> int:
        return {
            "RAID 0": 2,
            "RAID 1": 2,
            "RAID 5": 3,
            "RAID 6": 4,
            "RAID 10": 4,
        }.get(level, 2)

    def reset(self, level: Optional[str] = None, num_disks: Optional[int] = None) -> None:
        if level and level in self.LEVELS:
            self.level = level
        if num_disks is not None:
            self.num_disks = num_disks
        self.num_disks = max(self._min_disks(self.level), self.num_disks)
        # RAID 10 needs an even disk count (mirrored pairs)
        if self.level == "RAID 10" and self.num_disks % 2 == 1:
            self.num_disks += 1
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
            if all(d.blocks[i] is None for d in self.disks):
                return i
        return 0

    def write_page(self, pid: str, page: int) -> dict:
        key = f"{pid}:P{page}"
        data = f"{pid}-P{page}"
        idx = self._next_free_stripe_index()
        steps = [f"Write {data} using {self.level}"]

        if self.level == "RAID 0":
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

        elif self.level == "RAID 5":
            parity_disk = idx % self.num_disks
            data_disks = [d for i, d in enumerate(self.disks) if i != parity_disk]
            primary = data_disks[0]
            if not primary.failed:
                primary.blocks[idx] = data
            for j, d in enumerate(data_disks[1:], start=1):
                if not d.failed:
                    d.blocks[idx] = f"{data}/S{j}"
            parity_val = f"P({data})"
            if not self.disks[parity_disk].failed:
                self.disks[parity_disk].blocks[idx] = parity_val
            self.stored_pages[key] = [data, parity_val]
            steps.append(f"Data + single parity on Disk {parity_disk + 1} @ stripe {idx}")

        elif self.level == "RAID 6":
            # Two rotating parity disks (P and Q)
            p_disk = idx % self.num_disks
            q_disk = (idx + 1) % self.num_disks
            if q_disk == p_disk:
                q_disk = (p_disk + 1) % self.num_disks
            data_disks = [
                d for i, d in enumerate(self.disks) if i not in (p_disk, q_disk)
            ]
            if data_disks and not data_disks[0].failed:
                data_disks[0].blocks[idx] = data
            for j, d in enumerate(data_disks[1:], start=1):
                if not d.failed:
                    d.blocks[idx] = f"{data}/S{j}"
            p_val, q_val = f"P({data})", f"Q({data})"
            if not self.disks[p_disk].failed:
                self.disks[p_disk].blocks[idx] = p_val
            if not self.disks[q_disk].failed:
                self.disks[q_disk].blocks[idx] = q_val
            self.stored_pages[key] = [data, p_val, q_val]
            steps.append(
                f"Data + dual parity on Disks {p_disk + 1}/{q_disk + 1} @ stripe {idx}"
            )

        else:  # RAID 10 — stripe across mirrored pairs
            pairs = self.num_disks // 2
            pair = page % max(1, pairs)
            d0 = pair * 2
            d1 = d0 + 1
            stripe_tag = f"{data}/M{pair}"
            if d0 < len(self.disks) and not self.disks[d0].failed:
                self.disks[d0].blocks[idx] = stripe_tag
            if d1 < len(self.disks) and not self.disks[d1].failed:
                self.disks[d1].blocks[idx] = stripe_tag
            self.stored_pages[key] = [stripe_tag]
            steps.append(
                f"Striped to mirror pair {pair + 1} "
                f"(Disks {d0 + 1}+{d1 + 1}) @ block {idx}"
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
        target = next((d for d in self.disks if d.disk_id == disk_id), None)
        if target is None:
            return {"type": "DISK_FAILURE", "error": "Disk not found"}

        target.failed = True
        available = self.data_available()
        event = {
            "type": "DISK_FAILURE",
            "failed_disk": disk_id,
            "data_available": available,
            "recovery": self._recovery_plan(disk_id, available),
            "message": "DISK FAILURE DETECTED",
            "failed_count": sum(1 for d in self.disks if d.failed),
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
        if not self.data_available() and target.failed:
            # Still try if remaining redundancy is enough after marking online later;
            # block recovery when array is already past tolerance excluding this disk.
            others_failed = sum(1 for d in self.disks if d.failed and d.disk_id != disk_id)
            if self.level == "RAID 5" and others_failed >= 1:
                return {
                    "type": "RECOVERY",
                    "success": False,
                    "message": "Cannot rebuild: RAID 5 already beyond one-disk tolerance",
                }
            if self.level == "RAID 6" and others_failed >= 2:
                return {
                    "type": "RECOVERY",
                    "success": False,
                    "message": "Cannot rebuild: RAID 6 already beyond two-disk tolerance",
                }

        for i in range(self.capacity):
            donors = [d.blocks[i] for d in self.disks if not d.failed and d.blocks[i]]
            if not donors:
                continue
            if self.level == "RAID 1":
                target.blocks[i] = next(
                    (b for b in donors if not str(b).startswith(("P(", "Q("))), donors[0]
                )
            elif self.level == "RAID 10":
                # Rebuild from mirror partner in the same pair
                partner_idx = (disk_id - 1) ^ 1
                partner = next((d for d in self.disks if d.disk_id == partner_idx + 1), None)
                if partner and not partner.failed and partner.blocks[i] is not None:
                    target.blocks[i] = partner.blocks[i]
                else:
                    donor = next(
                        (b for b in donors if not str(b).startswith(("P(", "Q("))), None
                    )
                    if donor:
                        target.blocks[i] = f"REBUILT:{donor}"
            else:
                # RAID 5 / 6 parity rebuild (simulated)
                donor = next(
                    (b for b in donors if not str(b).startswith(("P(", "Q("))), donors[0]
                )
                target.blocks[i] = f"REBUILT:{donor}"

        target.failed = False
        self.recoveries += 1
        event = {
            "type": "RECOVERY",
            "success": True,
            "disk_id": disk_id,
            "message": f"Disk {disk_id} rebuilt using {self.level} redundancy",
        }
        self.last_event = event
        return event

    def data_available(self) -> bool:
        failed = sum(1 for d in self.disks if d.failed)
        if self.level == "RAID 0":
            return failed == 0
        if self.level == "RAID 1":
            return failed < self.num_disks
        if self.level == "RAID 5":
            return failed <= 1
        if self.level == "RAID 6":
            return failed <= 2
        if self.level == "RAID 10":
            # Survives one failure per mirrored pair
            pairs = self.num_disks // 2
            for pair in range(pairs):
                d0 = self.disks[pair * 2]
                d1 = self.disks[pair * 2 + 1]
                if d0.failed and d1.failed:
                    return False
            return True
        return failed == 0

    def _recovery_plan(self, disk_id: int, available: bool) -> str:
        if self.level == "RAID 0":
            return "No redundancy. Lost stripe data cannot be reconstructed."
        if self.level == "RAID 1":
            return (
                f"Mirror copy available. Rebuild Disk {disk_id} from surviving mirror."
                if available
                else "All mirrors failed."
            )
        if self.level == "RAID 5":
            return (
                f"Reconstruct Disk {disk_id} using single parity."
                if available
                else "Too many disks failed for RAID 5 (tolerates 1)."
            )
        if self.level == "RAID 6":
            return (
                f"Reconstruct Disk {disk_id} using dual parity (P+Q)."
                if available
                else "Too many disks failed for RAID 6 (tolerates 2)."
            )
        # RAID 10
        partner = ((disk_id - 1) ^ 1) + 1
        return (
            f"Rebuild Disk {disk_id} from mirror partner Disk {partner} "
            f"(stripe-of-mirrors)."
            if available
            else "A mirrored pair lost both disks; stripe data is unavailable."
        )

    def comparison(self) -> List[dict]:
        n = self.num_disks
        pairs = max(1, n // 2)
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
                "efficiency": f"{max(1, 100 // n)}%",
                "fault_tolerance": f"{n - 1} disks",
                "disks_required": "2+",
                "capacity_factor": 1,
            },
            {
                "level": "RAID 5",
                "read": "Good",
                "write": "Fair (parity)",
                "efficiency": f"{int((n - 1) / max(n, 1) * 100)}%",
                "fault_tolerance": "1 disk",
                "disks_required": "3+",
                "capacity_factor": max(1, n - 1),
            },
            {
                "level": "RAID 6",
                "read": "Good",
                "write": "Lower (dual parity)",
                "efficiency": f"{int((n - 2) / max(n, 1) * 100)}%",
                "fault_tolerance": "2 disks",
                "disks_required": "4+",
                "capacity_factor": max(1, n - 2),
            },
            {
                "level": "RAID 10",
                "read": "Excellent",
                "write": "Good",
                "efficiency": "50%",
                "fault_tolerance": "1 per mirror pair",
                "disks_required": "4+ (even)",
                "capacity_factor": pairs,
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
