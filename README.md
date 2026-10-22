# Research Centre HPC Resource Simulator

University of Limpopo · SCSB082 Advanced Operating Systems · Project Assessment 2026

Complete simulator for the research-centre HPC scenario:

Process → CPU → Main memory → Virtual memory → Secondary storage → RAID

## Run

```powershell
cd "C:\Users\budel\OneDrive\Documentos\Advanced OS"
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

You can also start the server directly from the project root:

```powershell
python app\main.py
```

## Features

- **Part A:** Custom processes, FCFS / Round Robin / SJF / Priority, Gantt chart
- **Part B:** Configurable RAM/page size, frames, page tables
- **Part C:** Page faults with visible recovery steps
- **Part D:** Virtual memory + FIFO / LRU / Optimal comparison
- **Part E:** RAID 0 / 1 / 5 / 6 / 10, disk failure and recovery
- **Integration:** Step through the full pipeline
- **Docs:** `docs/USER_MANUAL.md`

## Experiments

```powershell
python experiments/run_experiments.py
```

## Layout

```
app/main.py                 FastAPI entry
app/simulator/              CPU, memory, replacement, RAID, integration
static/                     Multi-page UI
test_data/                  Baseline workload
experiments/                Required experiment runner
docs/USER_MANUAL.md
```
