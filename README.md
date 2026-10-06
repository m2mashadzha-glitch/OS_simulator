# Operating System Resource Simulator

University of Limpopo · SCSB082 Advanced Operating Systems · Project Assessment 2026

Interactive simulator for process scheduling, paging, virtual memory, page replacement, and RAID storage.

## Quick start

```powershell
cd "C:\Users\budel\OneDrive\Documentos\Advanced OS"
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Git Bash:

```bash
source venv/Scripts/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**

## Features

- **Part A:** Processes, FCFS / Round Robin / SJF / Priority, Gantt, CPU metrics
- **Part B:** Configurable RAM/page size, frames, page tables
- **Part C:** Page hits/faults with visible recovery steps
- **Part D:** Virtual memory + FIFO / LRU / Optimal comparison
- **Part E:** RAID 0 / 1 / 5 / 6 / 10, disk failure and recovery
- **Integration:** Step / Start / Pause through the full pipeline
- **Demo scenario:** Large research process from the assessment brief

## Demo for the lecturer

1. Click **Load Demo Scenario**
2. Press **Step** repeatedly (or Start)
3. Watch page faults fill 16 KB RAM (4 frames)
4. Click **Disk Failure** (disk 2) → data still available on RAID 5
5. Click **Recover Disk**
6. Change algorithm / RAM / replacement / RAID and re-run

## Project layout

```
app/main.py              FastAPI entrypoint
app/simulator/           Simulation engine
static/                  Web UI
docs/USER_MANUAL.md      User manual
test_data/               Demo inputs
experiments/             Experiment helper script
```

## Experiments

```bash
python experiments/run_experiments.py
```

Results are written under `experiments/output/`.

## Spec

See `SCSB082 - Project Assessment 2026.pdf`.
