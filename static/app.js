let state = null;
let timer = null;

async function api(path, method = "GET", body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text() || res.statusText);
  return res.json();
}

function el(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const node = el(id);
  if (node) node.textContent = value;
}

function setHtml(id, value) {
  const node = el(id);
  if (node) node.innerHTML = value;
}

function on(id, event, handler) {
  const node = el(id);
  if (node) node.addEventListener(event, handler);
}

function setLed(on) {
  const led = el("run-led");
  if (led) led.classList.toggle("on", !!on);
}

function queueHtml(items) {
  if (!items.length) return `<span class="muted">— empty —</span>`;
  return items.map((p) => `<span class="qitem">${p.pid}</span>`).join("");
}

function metersHtml(pairs) {
  return pairs
    .map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`)
    .join("");
}

function flash(id) {
  const node = el(id);
  if (!node) return;
  node.classList.remove("flash");
  void node.offsetWidth;
  node.classList.add("flash");
}

function render(s) {
  const prevTime = state?.time;
  state = s;
  setText("sim-time", s.time);
  if (prevTime !== undefined && prevTime !== s.time) flash("sim-time");

  // Dashboard summary
  setText("sum-running", s.running ? s.running.pid : "IDLE");
  setText("sum-ready", s.ready.length);
  setText("sum-done", s.completed.length);
  setText("sum-faults", s.memory.page_faults);
  setText("sum-hits", s.memory.page_hits);
  setText("sum-raid", s.raid.level);
  setText("sum-avail", s.raid.data_available ? "YES" : "NO");
  setText("sum-algo", s.scheduler.algorithm);
  setText("sum-util", `${s.metrics.cpu_utilisation}%`);

  const hot = el("pipe-cpu");
  if (hot) {
    document.querySelectorAll(".pipe-step").forEach((n) => n.classList.remove("hot"));
    if (s.memory.last_event?.type === "PAGE_FAULT") el("pipe-vm")?.classList.add("hot");
    else if (s.running) el("pipe-cpu")?.classList.add("hot");
  }

  // Process table
  if (el("process-tbody")) {
    setHtml(
      "process-tbody",
      s.processes
        .map((p) => {
          const row = p.status === "Running" ? ' class="row-running"' : "";
          const st = `status status-${String(p.status).toLowerCase()}`;
          return `<tr${row}>
            <td>${p.pid}</td><td>${p.arrival}</td><td>${p.burst}</td><td>${p.remaining}</td>
            <td>${p.priority}</td><td>${p.size_kb}K</td><td>${p.num_pages}</td>
            <td><span class="${st}">${p.status}</span></td></tr>`;
        })
        .join("")
    );
  }

  // CPU
  if (el("cpu-panel")) {
    setText(
      "cpu-panel",
      s.running
        ? `> RUN ${s.running.pid}\n  burst=${s.running.burst}  rem=${s.running.remaining}\n  pri=${s.running.priority}  size=${s.running.size_kb}KB`
        : "> CPU IDLE\n  waiting for ready queue"
    );
  }
  setText(
    "sched-info",
    `${s.scheduler.algorithm} · quantum ${s.scheduler.quantum} · busy ${s.metrics.busy_time}/${s.time || 0}`
  );
  if (el("ready-queue")) setHtml("ready-queue", queueHtml(s.ready));
  if (el("completed")) setHtml("completed", queueHtml(s.completed));
  if (el("gantt")) {
    setHtml(
      "gantt",
      s.gantt
        .map((g) => {
          const cls = g.pid === "IDLE" ? "idle" : "run";
          return `<span class="${cls}" title="t=${g.time}">${g.pid}</span>`;
        })
        .join("")
    );
  }

  // Memory
  const m = s.memory;
  setText(
    "mem-meta",
    `RAM ${m.ram_size_kb}KB / page ${m.page_size_kb}KB → ${m.num_frames} frames · VM ${m.virtual_size_kb}KB (${m.num_virtual_pages} pages) · ${m.replacement}`
  );
  if (el("frames")) {
    setHtml(
      "frames",
      Object.entries(m.frames)
        .map(([id, f]) =>
          f.free
            ? `<div class="frame free">F${id}\nFREE</div>`
            : `<div class="frame used">F${id}\n${f.pid}:p${f.page}</div>`
        )
        .join("")
    );
  }
  if (el("pt-tbody")) {
    const rows = [];
    for (const [pid, entries] of Object.entries(m.page_tables)) {
      for (const e of entries) {
        rows.push(`<tr>
          <td>${pid}</td><td>${e.page}</td><td>${e.frame ?? "—"}</td>
          <td>${e.valid ? 1 : 0}</td><td>${e.dirty ? 1 : 0}</td><td>${e.location}</td>
        </tr>`);
      }
    }
    setHtml("pt-tbody", rows.join("") || `<tr><td colspan="6">no mappings</td></tr>`);
  }

  // Virtual memory
  if (el("vm-stats")) {
    setHtml(
      "vm-stats",
      metersHtml([
        ["Hits", m.page_hits],
        ["Faults", m.page_faults],
        ["Hit %", m.hit_rate],
        ["Fault %", m.fault_rate],
        ["Replace", m.replacements],
        ["Xfer", m.transfers],
        ["Mem %", m.memory_utilisation],
      ])
    );
  }
  if (el("fault-box")) {
    const box = el("fault-box");
    const fe = m.last_event;
    if (!fe) {
      box.className = "teletype";
      box.textContent = "MEM: idle — step to observe hit / fault path";
    } else {
      box.className = "teletype " + (fe.type === "PAGE_HIT" ? "hit" : "");
      box.textContent = `${fe.type}\n` + (fe.steps || []).join("\n");
    }
  }
  if (el("rep-tbody")) {
    setHtml(
      "rep-tbody",
      s.replacement_comparison
        .map(
          (r) => `<tr>
          <td>${r.algorithm}</td><td>${r.hits}</td><td>${r.faults}</td>
          <td>${r.hit_rate}</td><td>${r.fault_rate}</td></tr>`
        )
        .join("")
    );
  }

  // RAID
  const raid = s.raid;
  setText(
    "raid-meta",
    `${raid.level} · ${raid.num_disks} disks · R${raid.reads}/W${raid.writes} · available=${raid.data_available ? "YES" : "NO"} · util ${raid.storage_utilisation}%`
  );
  if (el("raid-disks")) {
    setHtml(
      "raid-disks",
      raid.disks
        .map((d) => {
          const blocks = d.blocks
            .map((b, i) => (b ? `${String(i).padStart(2, "0")} ${b}` : null))
            .filter(Boolean)
            .slice(0, 10)
            .join("\n");
          return `<div class="disk ${d.failed ? "failed" : ""}">
            <h4>DISK ${d.disk_id} · ${d.status}</h4>
            <pre>${blocks || "· empty ·"}</pre>
          </div>`;
        })
        .join("")
    );
  }
  if (el("raid-event")) {
    const rb = el("raid-event");
    const re = raid.last_event;
    if (!re) {
      rb.className = "teletype";
      rb.textContent = "RAID: quiet — pages land here on fault / demo load";
    } else if (re.type === "DISK_FAILURE") {
      rb.className = "teletype fail";
      rb.textContent =
        `${re.message}\nFailed: Disk ${re.failed_disk}\n` +
        `Available: ${re.data_available ? "YES" : "NO"}\n${re.recovery}`;
    } else {
      rb.className = "teletype";
      rb.textContent = `${re.type}\n` + (re.steps || [re.message || ""]).join("\n");
    }
  }
  if (el("raid-cmp")) {
    setHtml(
      "raid-cmp",
      raid.comparison
        .map(
          (c) => `<tr>
          <td>${c.level}</td><td>${c.read}</td><td>${c.write}</td>
          <td>${c.efficiency}</td><td>${c.fault_tolerance}</td><td>${c.disks_required}</td>
        </tr>`
        )
        .join("")
    );
  }

  // Metrics
  if (el("metrics")) {
    setHtml(
      "metrics",
      metersHtml([
        ["CPU %", s.metrics.cpu_utilisation],
        ["Wait", s.metrics.average_waiting_time],
        ["TAT", s.metrics.average_turnaround_time],
        ["Resp", s.metrics.average_response_time],
        ["Done", s.metrics.completed_count],
        ["RAID %", raid.storage_utilisation],
      ])
    );
  }
  if (el("log")) setText("log", (s.event_log || []).join("\n"));
}

async function refresh() {
  render(await api("/api/state"));
}

async function applyConfig() {
  const body = {};
  if (el("algorithm")) body.algorithm = el("algorithm").value;
  if (el("quantum")) body.quantum = Number(el("quantum").value);
  if (el("ram")) body.ram_size_kb = Number(el("ram").value);
  if (el("page")) body.page_size_kb = Number(el("page").value);
  if (el("virtual")) body.virtual_size_kb = Number(el("virtual").value);
  if (el("replacement")) body.replacement = el("replacement").value;
  if (el("raid")) body.raid_level = el("raid").value;
  if (el("disks")) body.num_disks = Number(el("disks").value);
  render(await api("/api/configure", "POST", body));
}

function syncControlsFromState(s) {
  if (!s) return;
  if (el("algorithm")) el("algorithm").value = s.scheduler.algorithm;
  if (el("quantum")) el("quantum").value = s.scheduler.quantum;
  if (el("ram")) el("ram").value = s.memory.ram_size_kb;
  if (el("page")) el("page").value = s.memory.page_size_kb;
  if (el("virtual")) el("virtual").value = s.memory.virtual_size_kb;
  if (el("replacement")) el("replacement").value = s.memory.replacement;
  if (el("raid")) el("raid").value = s.raid.level;
  if (el("disks")) el("disks").value = s.raid.num_disks;
}

function startAuto() {
  if (timer) return;
  setLed(true);
  timer = setInterval(async () => {
    const s = await api("/api/step", "POST");
    render(s);
    if (s.processes.length && s.processes.every((p) => p.status === "Terminated")) {
      pauseAuto();
    }
  }, 450);
}

function pauseAuto() {
  if (timer) clearInterval(timer);
  timer = null;
  setLed(false);
}

function bindControls() {
  on("btn-generate", "click", async () => {
    pauseAuto();
    const s = await api("/api/generate-processes", "POST");
    syncControlsFromState(s);
    render(s);
  });
  on("btn-demo", "click", async () => {
    pauseAuto();
    const s = await api("/api/demo", "POST");
    syncControlsFromState(s);
    render(s);
  });
  on("btn-step", "click", async () => render(await api("/api/step", "POST")));
  on("btn-start", "click", () => startAuto());
  on("btn-pause", "click", () => pauseAuto());
  on("btn-run20", "click", async () => render(await api("/api/run", "POST", { steps: 20 })));
  on("btn-reset", "click", async () => {
    pauseAuto();
    const s = await api("/api/reset", "POST");
    syncControlsFromState(s);
    render(s);
  });
  on("btn-apply", "click", () => applyConfig());
  on("btn-fail", "click", async () =>
    render(await api("/api/fail-disk", "POST", { disk_id: Number(el("fail-id")?.value || 2) }))
  );
  on("btn-recover", "click", async () =>
    render(await api("/api/recover-disk", "POST", { disk_id: Number(el("fail-id")?.value || 2) }))
  );
}

bindControls();
refresh().then(() => syncControlsFromState(state));
