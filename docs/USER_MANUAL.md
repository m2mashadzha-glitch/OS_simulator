# User Manual — Research Centre HPC Resource Simulator

**Module:** SCSB082 Advanced Operating Systems  
**Project:** Design and Development of an Operating Systems Resource Management Simulator  
**Institution:** University of Limpopo  

Concept explanations are paraphrased from standard OS material, including William Stallings, *Operating Systems: Internals and Design Principles*.

## 1. Install and run

```powershell
cd "C:\Users\budel\OneDrive\Documentos\Advanced OS"
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## 2. Screens

| Page | Assessment focus |
|------|------------------|
| Processes | Part A — process states, ready queue, CPU scheduling, Gantt |
| Memory | Parts B & C — frames, page tables, page faults |
| Virtual Memory | Part D — virtual vs physical size, FIFO/LRU/Optimal |
| RAID / Disk | Part E — RAID layout, failure, recovery |
| Metrics | Performance dashboard (§15) |

## 3. Suggested walkthrough

1. **Processes** — enter or load processes, choose a scheduler, use Step/Play.
2. **Memory** — show frames and page tables; Step to trigger hits/faults.
3. **Virtual Memory** — Compare FIFO/LRU/Optimal on the reference string.
4. **RAID** — choose a level, fail a disk, recover if data remains available.
5. **Metrics** — read CPU, memory, virtual-memory and RAID counters.

## 4. Concepts you should be able to explain

### CPU scheduling
The scheduler chooses the next ready process. FCFS, SJF and Priority are non-preemptive in this build; Round Robin preempts after a time quantum.

### Paging
Each process is split into fixed-size pages; RAM is split into frames of the same size. The page table stores frame number, valid bit and dirty bit.

### Page fault
If the valid bit is 0, the OS fetches the page from secondary storage, optionally evicts a victim, updates the page table, then resumes.

### Virtual memory
Virtual address space can exceed physical RAM. Only referenced pages need to be resident.

### Replacement
- **FIFO** — oldest resident page  
- **LRU** — least recently used page  
- **Optimal** — page not needed for the longest future time (benchmark)

### RAID
RAID 0 stripes with no protection; RAID 1 mirrors; RAID 5/6 use parity; RAID 10 stripes mirrors. Redundant levels can reconstruct data after failure.

## 5. Experiments

```powershell
python experiments/run_experiments.py
```

Results: `experiments/output/experiment_results.json`

## 6. Custom processes

On **Processes**, edit PID/arrival/burst/priority/size/memory, then **Apply processes**. PIDs are normalised to `P1`, `P2`, …
