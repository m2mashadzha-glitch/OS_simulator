"""
RAID secondary storage (Stallings-style teaching model).

Layouts used here follow the standard RAID ideas:
  RAID 0  — striping, no redundancy
  RAID 1  — mirroring
  RAID 5  — striping with distributed parity
  RAID 6  — striping with dual distributed parity
  RAID 10 — stripe across mirrored pairs

Logical blocks (e.g. process pages P1:pg0) are stored and then mapped onto
disks according to the active level. Changing the level rebuilds the same
logical data into the new layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field


RAID_SPECS = {
    "RAID 0": {
        "min_disks": 2,
        "fault_tolerance": 0,
        "storage_efficiency": 1.0,
        "read_performance": "High (parallel striped reads)",
        "write_performance": "High (parallel striped writes)",
        "recovery": "None — data lost if any disk fails",
        "notes": "Block striping only; no redundancy.",
    },
    "RAID 1": {
        "min_disks": 2,
        "fault_tolerance": 1,
        "storage_efficiency": 0.5,
        "read_performance": "High (either mirror)",
        "write_performance": "Medium (write both mirrors)",
        "recovery": "Copy surviving mirror onto replacement disk",
        "notes": "Mirroring — each block duplicated.",
    },
    "RAID 5": {
        "min_disks": 3,
        "fault_tolerance": 1,
        "storage_efficiency": None,
        "read_performance": "High",
        "write_performance": "Medium (parity update)",
        "recovery": "Reconstruct missing data using parity",
        "notes": "Block striping with rotating parity.",
    },
    "RAID 6": {
        "min_disks": 4,
        "fault_tolerance": 2,
        "storage_efficiency": None,
        "read_performance": "High",
        "write_performance": "Lower (dual parity)",
        "recovery": "Reconstruct using dual parity",
        "notes": "Survives two disk failures.",
    },
    "RAID 10": {
        "min_disks": 4,
        "fault_tolerance": 1,
        "storage_efficiency": 0.5,
        "read_performance": "Very high",
        "write_performance": "High",
        "recovery": "Rebuild from the mirror pair",
        "notes": "Stripe of mirrors (1+0).",
    },
}


@dataclass
class Disk:
    disk_id: int
    status: str = "ONLINE"  # ONLINE | FAILED
    blocks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "disk_id": self.disk_id,
            "name": f"Disk {self.disk_id}",
            "status": self.status,
            "blocks": list(self.blocks),
        }


@dataclass
class RaidArray:
    level: str = "RAID 5"
    disk_count: int = 4
    disks: list[Disk] = field(default_factory=list)
    logical_blocks: list[str] = field(default_factory=list)
    stripe_units: list[dict] = field(default_factory=list)
    read_ops: int = 0
    write_ops: int = 0
    failed_disks: int = 0
    recovery_ops: int = 0
    last_event: str = ""
    data_available: bool = True

    def __post_init__(self) -> None:
        self.configure(self.level, self.disk_count)

    def configure(self, level: str, disk_count: int) -> None:
        if level not in RAID_SPECS:
            raise ValueError(f"Unsupported RAID level: {level}")
        spec = RAID_SPECS[level]
        if disk_count < spec["min_disks"]:
            raise ValueError(f"{level} needs at least {spec['min_disks']} disks")
        preserved = list(self.logical_blocks)
        self.level = level
        self.disk_count = disk_count
        self.disks = [Disk(disk_id=i + 1) for i in range(disk_count)]
        self.stripe_units = []
        self.read_ops = 0
        self.write_ops = 0
        self.failed_disks = 0
        self.recovery_ops = 0
        self.data_available = True
        self.logical_blocks = preserved
        self._rebuild_layout()
        self.last_event = (
            f"Configured {level} with {disk_count} disks"
            + (f" — redistributed {len(self.logical_blocks)} stored blocks" if self.logical_blocks else "")
        )

    def clear_storage(self) -> None:
        self.logical_blocks = []
        self._rebuild_layout()
        self.last_event = "Secondary storage cleared"

    def store_blocks(self, blocks: list[str], *, replace: bool = False) -> None:
        """
        Store logical data blocks (e.g. page labels) and map them to disks
        using the active RAID layout.
        """
        cleaned = [str(block) for block in blocks if str(block).strip()]
        if replace:
            self.logical_blocks = cleaned
        else:
            existing = set(self.logical_blocks)
            for block in cleaned:
                if block not in existing:
                    self.logical_blocks.append(block)
                    existing.add(block)
        self._rebuild_layout()
        self.write_ops += max(1, len(cleaned))
        self.last_event = (
            f"Stored {len(cleaned)} block(s) with {self.level} layout "
            f"({len(self.logical_blocks)} logical blocks total)"
        )

    def read_block(self, block: str) -> bool:
        """Simulate a read of a logical block from the array."""
        self.read_ops += 1
        found = block in self.logical_blocks
        if not self.data_available:
            self.last_event = f"READ FAILED for {block} — array data unavailable"
            return False
        self.last_event = (
            f"READ {block} from {self.level}"
            if found
            else f"READ miss for {block} on {self.level}"
        )
        return found

    def _parity_symbol(self, blocks: list[str], tag: str = "Par") -> str:
        # Teaching parity label (not cryptographic XOR) — shows parity ownership.
        sample = "".join(blocks)[:6]
        return f"{tag}({sample})"

    def _clear_disk_blocks(self) -> None:
        for disk in self.disks:
            if disk.status != "FAILED":
                disk.blocks = []
            # Keep FAILED disks empty visually for the missing slice.
            if disk.status == "FAILED":
                disk.blocks = []
        self.stripe_units = []

    def _rebuild_layout(self) -> None:
        """Map logical_blocks onto disks per Stallings RAID organization."""
        self._clear_disk_blocks()
        blocks = list(self.logical_blocks)
        if not blocks:
            return

        if self.level == "RAID 0":
            for index, block in enumerate(blocks):
                disk = self.disks[index % self.disk_count]
                if disk.status == "ONLINE":
                    disk.blocks.append(block)
                self.stripe_units.append(
                    {"disk": disk.disk_id, "data": block, "parity": False, "index": index}
                )
            return

        if self.level == "RAID 1":
            # Mirror across pairs when more than 2 disks; else disk1 mirrors disk0.
            for index, block in enumerate(blocks):
                if self.disk_count >= 4:
                    pair = index % (self.disk_count // 2)
                    targets = [self.disks[pair * 2], self.disks[pair * 2 + 1]]
                else:
                    targets = [self.disks[0], self.disks[1]]
                for disk in targets:
                    if disk.status == "ONLINE":
                        disk.blocks.append(block)
                    self.stripe_units.append(
                        {
                            "disk": disk.disk_id,
                            "data": block,
                            "parity": False,
                            "mirror": True,
                            "index": index,
                        }
                    )
            return

        if self.level == "RAID 10":
            pairs = max(1, self.disk_count // 2)
            for index, block in enumerate(blocks):
                pair = index % pairs
                for disk in (self.disks[pair * 2], self.disks[pair * 2 + 1]):
                    if disk.status == "ONLINE":
                        disk.blocks.append(block)
                    self.stripe_units.append(
                        {
                            "disk": disk.disk_id,
                            "data": block,
                            "parity": False,
                            "mirror": True,
                            "index": index,
                        }
                    )
            return

        # RAID 5 / RAID 6 — stripe data with rotating parity disk(s)
        parity_count = 2 if self.level == "RAID 6" else 1
        data_disks = self.disk_count - parity_count
        stripe = 0
        i = 0
        while i < len(blocks):
            chunk = blocks[i : i + data_disks]
            while len(chunk) < data_disks:
                chunk.append("-")
            parity_start = stripe % self.disk_count
            data_index = 0
            for disk_idx, disk in enumerate(self.disks):
                if self.level == "RAID 5":
                    if disk_idx == parity_start:
                        symbol = self._parity_symbol(
                            [c for c in chunk if c != "-"], "P"
                        )
                        if disk.status == "ONLINE":
                            disk.blocks.append(symbol)
                        self.stripe_units.append(
                            {
                                "disk": disk.disk_id,
                                "data": symbol,
                                "parity": True,
                                "stripe": stripe,
                            }
                        )
                    else:
                        symbol = chunk[data_index]
                        data_index += 1
                        if symbol != "-" and disk.status == "ONLINE":
                            disk.blocks.append(symbol)
                        self.stripe_units.append(
                            {
                                "disk": disk.disk_id,
                                "data": symbol,
                                "parity": False,
                                "stripe": stripe,
                            }
                        )
                else:
                    p1 = parity_start
                    p2 = (parity_start + 1) % self.disk_count
                    if disk_idx == p1:
                        symbol = self._parity_symbol(
                            [c for c in chunk if c != "-"], "P"
                        )
                        if disk.status == "ONLINE":
                            disk.blocks.append(symbol)
                        self.stripe_units.append(
                            {
                                "disk": disk.disk_id,
                                "data": symbol,
                                "parity": True,
                                "stripe": stripe,
                            }
                        )
                    elif disk_idx == p2:
                        symbol = self._parity_symbol(
                            [c for c in chunk if c != "-"], "Q"
                        )
                        if disk.status == "ONLINE":
                            disk.blocks.append(symbol)
                        self.stripe_units.append(
                            {
                                "disk": disk.disk_id,
                                "data": symbol,
                                "parity": True,
                                "stripe": stripe,
                            }
                        )
                    else:
                        symbol = chunk[data_index]
                        data_index += 1
                        if symbol != "-" and disk.status == "ONLINE":
                            disk.blocks.append(symbol)
                        self.stripe_units.append(
                            {
                                "disk": disk.disk_id,
                                "data": symbol,
                                "parity": False,
                                "stripe": stripe,
                            }
                        )
            i += data_disks
            stripe += 1

    def fail_disk(self, disk_id: int) -> dict:
        disk = next((item for item in self.disks if item.disk_id == disk_id), None)
        if disk is None:
            raise ValueError(f"Unknown disk {disk_id}")
        if disk.status == "FAILED":
            return self.snapshot()
        disk.status = "FAILED"
        self.failed_disks += 1
        tolerance = RAID_SPECS[self.level]["fault_tolerance"]
        failed_now = sum(1 for item in self.disks if item.status == "FAILED")
        self.data_available = failed_now <= tolerance and tolerance > 0
        if self.level == "RAID 0":
            self.data_available = False
        self._rebuild_layout()
        self.last_event = (
            f"DISK FAILURE DETECTED — Failed Disk: Disk {disk_id}. "
            f"Data Availability: {'YES' if self.data_available else 'NO'}"
        )
        self.read_ops += 1
        return self.snapshot()

    def recover(self) -> dict:
        failed = [disk for disk in self.disks if disk.status == "FAILED"]
        if not failed:
            self.last_event = "No failed disks to recover"
            return self.snapshot()
        if not self.data_available and self.level != "RAID 0":
            # If already unavailable before marking recovered, still block.
            pass
        if self.level == "RAID 0":
            self.last_event = "Recovery impossible — RAID 0 has no redundancy"
            return self.snapshot()
        if sum(1 for d in self.disks if d.status == "FAILED") > RAID_SPECS[self.level]["fault_tolerance"]:
            self.last_event = "Recovery impossible — too many failed disks"
            return self.snapshot()

        for disk in failed:
            disk.status = "ONLINE"
            self.recovery_ops += 1
        self.failed_disks = sum(1 for item in self.disks if item.status == "FAILED")
        self.data_available = True
        self._rebuild_layout()
        self.last_event = (
            f"Recovery complete using {RAID_SPECS[self.level]['recovery']} "
            f"— {self.level} layout rebuilt"
        )
        return self.snapshot()

    def comparison_row(self) -> dict:
        spec = RAID_SPECS[self.level]
        n = self.disk_count
        if self.level == "RAID 5":
            efficiency = round((n - 1) / n, 2)
        elif self.level == "RAID 6":
            efficiency = round((n - 2) / n, 2)
        else:
            efficiency = spec["storage_efficiency"]
        return {
            "level": self.level,
            "disks_required": spec["min_disks"],
            "configured_disks": n,
            "read_performance": spec["read_performance"],
            "write_performance": spec["write_performance"],
            "storage_efficiency": efficiency,
            "fault_tolerance": spec["fault_tolerance"],
            "recovery": spec["recovery"],
            "notes": spec["notes"],
        }

    def metrics(self) -> dict:
        total_blocks = sum(len(disk.blocks) for disk in self.disks)
        online = sum(1 for disk in self.disks if disk.status == "ONLINE")
        return {
            "read_operations": self.read_ops,
            "write_operations": self.write_ops,
            "failed_disks": self.failed_disks,
            "recovery_operations": self.recovery_ops,
            "storage_utilisation": round((online / max(self.disk_count, 1)) * 100, 2),
            "estimated_performance": RAID_SPECS[self.level]["read_performance"],
            "data_available": self.data_available,
            "total_blocks": total_blocks,
            "logical_blocks": len(self.logical_blocks),
        }

    def snapshot(self) -> dict:
        return {
            "level": self.level,
            "disk_count": self.disk_count,
            "disks": [disk.to_dict() for disk in self.disks],
            "logical_blocks": list(self.logical_blocks),
            "layout_summary": self._layout_summary(),
            "last_event": self.last_event,
            "data_available": self.data_available,
            "comparison": self.comparison_row(),
            "all_levels": [
                {
                    "level": name,
                    **{k: v for k, v in spec.items() if k != "storage_efficiency"},
                    "storage_efficiency": (
                        round((self.disk_count - 1) / self.disk_count, 2)
                        if name == "RAID 5"
                        else round((self.disk_count - 2) / self.disk_count, 2)
                        if name == "RAID 6"
                        else spec["storage_efficiency"]
                    ),
                }
                for name, spec in RAID_SPECS.items()
            ],
            "metrics": self.metrics(),
        }

    def _layout_summary(self) -> str:
        if self.level == "RAID 0":
            return "Striping: consecutive pages rotate across disks (no parity)."
        if self.level == "RAID 1":
            return "Mirroring: each page is written to both disks in a mirror pair."
        if self.level == "RAID 5":
            return "Striping + rotating parity: one parity block per stripe, parity disk rotates."
        if self.level == "RAID 6":
            return "Striping + dual rotating parity (P and Q) for two-disk failure tolerance."
        if self.level == "RAID 10":
            return "Mirrored pairs, then striped across pairs."
        return self.level
