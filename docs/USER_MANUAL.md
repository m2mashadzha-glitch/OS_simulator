# User Manual — Operating System Resource Simulator

## 1. Purpose

This application simulates how an operating system manages processes, CPU time, main memory, virtual memory, and RAID storage. It is a teaching/demo tool, not a real OS kernel.

## 2. Requirements

- Python 3.10+ (tested with 3.14)
- Packages in `requirements.txt`

## 3. Installation

1. Open a terminal in the project folder.
2. Create and activate a virtual environment.
3. Run `python -m pip install -r requirements.txt`.
4. Start the server: `uvicorn app.main:app --reload`.
5. Open `http://127.0.0.1:8000` in a browser.

## 4. Main controls

| Control | Action |
|---------|--------|
| Generate Processes | Loads sample processes P1–P5 from the brief |
| Load Demo Scenario | Loads the required large research process scenario |
| Step | Advances one simulation time unit |
| Start / Pause | Auto-run / stop auto-run |
| Run ×20 | Fast-forward 20 steps |
| Reset | Clears state but keeps configuration |
| Apply Config | Applies CPU, memory, VM, RAID settings |
| Disk Failure | Marks the selected disk as failed |
| Recover Disk | Rebuilds a failed disk when the RAID level allows it |

## 5. Panels

- **Process:** ID, arrival, burst, remaining, priority, size, pages, status
- **CPU:** Running process, ready queue, completed list, Gantt chart
- **Memory:** Frame occupancy and page tables
- **Virtual Memory:** Hits/faults, fault steps, replacement algorithm comparison
- **RAID:** Per-disk contents, failure/recovery messages, level comparison
- **Performance:** CPU utilisation, waiting/turnaround/response averages, event log

## 6. Recommended demo path

1. Load Demo Scenario.
2. Step until several page faults occur.
3. Show that only 4 frames exist while the process has more virtual pages.
4. Trigger Disk Failure on Disk 2 under RAID 5 → Data Availability YES.
5. Recover Disk.
6. Switch replacement algorithm to FIFO vs LRU and compare the table.
7. Switch RAID level to RAID 0, fail a disk → Data Availability NO.

## 7. Tips for viva / demonstration

- Explain why a page fault happens (referenced page not in RAM).
- Explain why LRU often beats FIFO on repeating reference patterns.
- Explain why RAID 5 survives one disk failure and RAID 0 does not.
- Change RAM size and show the effect on fault rate.
