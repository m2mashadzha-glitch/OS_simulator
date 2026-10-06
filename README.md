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

## Pages

| URL | Content |
|-----|---------|
| `/` | Dashboard, pipeline overview, global config |
| `/cpu` | Processes, scheduler, ready queue, Gantt |
| `/memory` | Frames + page tables |
| `/virtual` | Hits/faults + replacement comparison |
| `/raid` | RAID 0/1/5/6/10, fail/recover |
| `/metrics` | Performance meters + kernel log |

## Features

- **Part A:** Processes, FCFS / Round Robin / SJF / Priority, Gantt, CPU metrics
- **Part B:** Configurable RAM/page size, frames, page tables
- **Part C:** Page hits/faults with visible recovery steps
- **Part D:** Virtual memory + FIFO / LRU / Optimal comparison
- **Part E:** RAID 0 / 1 / 5 / 6 / 10, disk failure and recovery
- **Integration:** Step / Start / Pause through the full pipeline
- **Demo scenario:** Large research process from the assessment brief

## Demo for the lecturer

1. On **Home**, click **Demo Scenario**
2. Open **CPU** → Step through scheduling
3. Open **Memory** / **Virtual Mem** → show faults and frames
4. Open **RAID** → Fail disk 2 (RAID 5 still available), then Recover
5. Open **Metrics** for averages and the event log

## Project layout

```
app/main.py              FastAPI entrypoint + page routes
app/simulator/           Simulation engine
static/*.html            Multi-page UI
static/style.css         Shared styles
static/app.js            Shared controls/renderer
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
