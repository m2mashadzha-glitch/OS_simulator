"""Helper to emit consistent page HTML. Run: python static/_page_shell.py"""
from pathlib import Path

FONT = (
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700"
    "&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap"
)

NAV = [
    ("/", "01", "Home", "home"),
    ("/cpu", "02", "CPU", "cpu"),
    ("/memory", "03", "Memory", "memory"),
    ("/virtual", "04", "Virtual Mem", "virtual"),
    ("/raid", "05", "RAID", "raid"),
    ("/metrics", "06", "Metrics", "metrics"),
]


def nav_html(active: str) -> str:
    links = []
    for href, idx, label, key in NAV:
        cls = ' class="active"' if key == active else ""
        links.append(f'<a{cls} href="{href}"><span class="idx">{idx}</span>{label}</a>')
    return "\n        ".join(links)


def page(
    key: str,
    title: str,
    subtitle: str,
    heading: str,
    blurb: str,
    toolbar_extra: str,
    body: str,
    footer_right: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} · OS Resource Bench</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="{FONT}" rel="stylesheet" />
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body data-page="{key}">
  <div class="shell">
    <aside class="rail">
      <div class="rail-brand">
        <div class="mark">OS</div>
        <div>
          <h1>Resource Bench</h1>
          <p>SCSB082 · Limpopo</p>
        </div>
      </div>
      <nav class="rail-nav">
        {nav_html(key)}
      </nav>
      <div class="rail-clock">
        <div class="led" id="run-led"></div>
        <div><small>Sim time</small><strong id="sim-time">0</strong></div>
      </div>
    </aside>

    <div class="stage">
      <div class="stage-bar">
        <div>
          <h2>{heading}</h2>
          <p>{blurb}</p>
        </div>
        <div class="dock">
          <div class="group">
            <button id="btn-step" class="btn primary">Step</button>
            <button id="btn-start" class="btn">Start</button>
            <button id="btn-pause" class="btn">Pause</button>
            <button id="btn-run20" class="btn">×20</button>
            <button id="btn-reset" class="btn warn">Reset</button>
          </div>
          <div class="group">
            <button id="btn-demo" class="btn dark">Demo</button>
          </div>
          {toolbar_extra}
        </div>
      </div>

{body}

      <footer class="footer">
        <span>{subtitle}</span>
        <span>{footer_right}</span>
      </footer>
    </div>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
"""


PAGES = {
    "cpu.html": dict(
        key="cpu",
        title="CPU",
        subtitle="Page: CPU",
        heading="CPU / Jobs",
        blurb="Process table, ready queue, running job, and Gantt chart.",
        footer_right="Part A · Scheduling",
        toolbar_extra="""<div class="group">
            <label class="field">Algorithm
              <select id="algorithm">
                <option>FCFS</option><option>Round Robin</option><option>SJF</option><option>Priority</option>
              </select>
            </label>
            <label class="field">Quantum<input id="quantum" type="number" min="1" value="4" /></label>
            <button id="btn-apply" class="btn primary">Apply</button>
          </div>""",
        body="""      <div class="grid two">
        <section class="panel">
          <h3><span class="num">01</span>Process table</h3>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>PID</th><th>Arr</th><th>Burst</th><th>Rem</th>
                  <th>Pri</th><th>Size</th><th>Pages</th><th>State</th>
                </tr>
              </thead>
              <tbody id="process-tbody"></tbody>
            </table>
          </div>
        </section>
        <section class="panel">
          <h3><span class="num">02</span>CPU</h3>
          <div id="cpu-panel" class="crt">IDLE</div>
          <p class="meta" id="sched-info"></p>
          <h3 style="margin-top:0.95rem">Ready</h3>
          <div id="ready-queue" class="queue"></div>
          <h3 style="margin-top:0.95rem">Completed</h3>
          <div id="completed" class="queue"></div>
          <h3 style="margin-top:0.95rem">Gantt</h3>
          <div id="gantt" class="gantt"></div>
        </section>
      </div>""",
    ),
    "memory.html": dict(
        key="memory",
        title="Memory",
        subtitle="Page: Memory",
        heading="Main Memory",
        blurb="Frames in RAM and page-table mappings.",
        footer_right="Part B · Paging",
        toolbar_extra="""<div class="group">
            <label class="field">RAM KB<input id="ram" type="number" min="4" value="32" /></label>
            <label class="field">Page KB<input id="page" type="number" min="1" value="4" /></label>
            <button id="btn-apply" class="btn primary">Apply</button>
          </div>""",
        body="""      <section class="panel" style="margin-bottom:0.85rem">
        <h3><span class="num">03</span>Physical frames</h3>
        <p class="meta" id="mem-meta"></p>
        <div id="frames" class="frames"></div>
      </section>
      <section class="panel">
        <h3><span class="num">04</span>Page table</h3>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Proc</th><th>Page</th><th>Frame</th><th>V</th><th>D</th><th>Loc</th></tr>
            </thead>
            <tbody id="pt-tbody"></tbody>
          </table>
        </div>
      </section>""",
    ),
    "virtual.html": dict(
        key="virtual",
        title="Virtual Memory",
        subtitle="Page: Virtual Memory",
        heading="Virtual Memory",
        blurb="Hit/fault path and replacement algorithm bake-off.",
        footer_right="Parts C–D",
        toolbar_extra="""<div class="group">
            <label class="field">Virtual KB<input id="virtual" type="number" min="4" value="64" /></label>
            <label class="field">Replace
              <select id="replacement"><option>FIFO</option><option>LRU</option><option>Optimal</option></select>
            </label>
            <button id="btn-apply" class="btn primary">Apply</button>
          </div>""",
        body="""      <section class="panel" style="margin-bottom:0.85rem">
        <h3><span class="num">05</span>VM counters</h3>
        <div id="vm-stats" class="meters"></div>
        <div id="fault-box" class="teletype" style="margin-top:0.75rem"></div>
      </section>
      <section class="panel">
        <h3><span class="num">06</span>Replacement bake-off</h3>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Algo</th><th>Hits</th><th>Faults</th><th>Hit%</th><th>Fault%</th></tr>
            </thead>
            <tbody id="rep-tbody"></tbody>
          </table>
        </div>
      </section>""",
    ),
    "raid.html": dict(
        key="raid",
        title="RAID",
        subtitle="Page: RAID",
        heading="RAID Storage",
        blurb="RAID 0 / 1 / 5 / 6 / 10 with failure and recovery.",
        footer_right="Part E · Storage",
        toolbar_extra="""<div class="group">
            <label class="field">RAID
              <select id="raid">
                <option>RAID 0</option><option>RAID 1</option><option selected>RAID 5</option>
                <option>RAID 6</option><option>RAID 10</option>
              </select>
            </label>
            <label class="field">Disks<input id="disks" type="number" min="2" value="4" /></label>
            <button id="btn-apply" class="btn primary">Apply</button>
          </div>
          <div class="group">
            <label class="field">Fail #<input id="fail-id" type="number" min="1" value="2" /></label>
            <button id="btn-fail" class="btn warn">Fail</button>
            <button id="btn-recover" class="btn">Recover</button>
          </div>""",
        body="""      <section class="panel" style="margin-bottom:0.85rem">
        <h3><span class="num">07</span>Disk array</h3>
        <p class="meta" id="raid-meta"></p>
        <div id="raid-disks" class="raid-grid"></div>
        <div id="raid-event" class="teletype" style="margin-top:0.75rem"></div>
      </section>
      <section class="panel">
        <h3><span class="num">08</span>Level matrix</h3>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Level</th><th>Read</th><th>Write</th><th>Eff.</th>
                <th>Tolerance</th><th>Min disks</th>
              </tr>
            </thead>
            <tbody id="raid-cmp"></tbody>
          </table>
        </div>
      </section>""",
    ),
    "metrics.html": dict(
        key="metrics",
        title="Metrics",
        subtitle="Page: Metrics",
        heading="Metrics / Log",
        blurb="Performance meters and the step-by-step kernel log.",
        footer_right="Experiments evidence",
        toolbar_extra="""<div class="group">
            <button id="btn-generate" class="btn ghost">P1–P5</button>
          </div>""",
        body="""      <section class="panel" style="margin-bottom:0.85rem">
        <h3><span class="num">09</span>Performance</h3>
        <div id="metrics" class="meters"></div>
      </section>
      <section class="panel">
        <h3><span class="num">10</span>Kernel log</h3>
        <pre id="log" class="kernellog"></pre>
      </section>""",
    ),
}


def main() -> None:
    root = Path(__file__).resolve().parent
    for name, cfg in PAGES.items():
        (root / name).write_text(page(**cfg), encoding="utf-8")
        print("wrote", name)


if __name__ == "__main__":
    main()
