let state = null;
let timer = null;

async function api(path, method = "GET", body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function el(id) {
  return document.getElementById(id);
}

function setLed(on) {
  el("run-led").classList.toggle("on", !!on);
}

function queueHtml(items) {
  if (!items.length) return `<span class="muted">— empty —</span>`;
  return items.map((p) => `<span class="qitem">${p.pid}</span>`).join("");
}

function render(s) {
  state = s;
  el("sim-time").textContent = s.time;

  el("process-tbody").innerHTML = s.processes
    .map((p) => {
      const row = p.status === "Running" ? ' class="row-running"' : "";
      const st = `status status-${String(p.status).toLowerCase()}`;
      return `<tr${row}>
      <td>${p.pid}</td><td>${p.arrival}</td><td>${p.burst}</td><td>${p.remaining}</td>
      <td>${p.priority}</td><td>${p.size_kb}K</td><td>${p.num_pages}</td>
      <td><span class="${st}">${p.status}</span></td></tr>`;
    })
    .join("");

  if (s.running) {
    el("cpu-panel").textContent =
      `> RUN ${s.running.pid}\n` +
      `  burst=${s.running.burst}  rem=${s.running.remaining}\n` +
      `  pri=${s.running.priority}  size=${s.running.size_kb}KB`;
  } else {
    el("cpu-panel").textContent = "> CPU IDLE\n  waiting for ready queue";
  }

  el("sched-info").textContent =
    `${s.scheduler.algorithm}  ·  quantum ${s.scheduler.quantum}  ·  busy ${s.metrics.busy_time}/${s.time || 0}`;

  el("ready-queue").innerHTML = queueHtml(s.ready);
  el("completed").innerHTML = queueHtml(s.completed);

  el("gantt").innerHTML = s.gantt
    .map((g) => {
      const cls = g.pid === "IDLE" ? "idle" : "run";
      return `<span class="${cls}" title="t=${g.time}">${g.pid}</span>`;
    })
    .join("");

  const m = s.memory;
  el("mem-meta").textContent =
    `RAM ${m.ram_size_kb}KB / page ${m.page_size_kb}KB → ${m.num_frames} frames · ` +
    `VM ${m.virtual_size_kb}KB (${m.num_virtual_pages} pages) · ${m.replacement}`;

  el("frames").innerHTML = Object.entries(m.frames)
    .map(([id, f]) => {
      if (f.free) return `<div class="frame free">F${id}\nFREE</div>`;
      return `<div class="frame used">F${id}\n${f.pid}:p${f.page}</div>`;
    })
    .join("");

  const rows = [];
  for (const [pid, entries] of Object.entries(m.page_tables)) {
    for (const e of entries) {
      rows.push(`<tr>
        <td>${pid}</td><td>${e.page}</td><td>${e.frame ?? "—"}</td>
        <td>${e.valid ? 1 : 0}</td><td>${e.dirty ? 1 : 0}</td><td>${e.location}</td>
      </tr>`);
    }
  }
  el("pt-tbody").innerHTML = rows.join("") || `<tr><td colspan="6">no mappings</td></tr>`;

  el("vm-stats").innerHTML = [
    ["Hits", m.page_hits],
    ["Faults", m.page_faults],
    ["Hit %", m.hit_rate],
    ["Fault %", m.fault_rate],
    ["Replace", m.replacements],
    ["Xfer", m.transfers],
    ["Mem %", m.memory_utilisation],
  ]
    .map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`)
    .join("");

  const fe = m.last_event;
  const box = el("fault-box");
  if (!fe) {
    box.className = "teletype";
    box.textContent = "MEM: idle — step to observe hit / fault path";
  } else {
    box.className = "teletype " + (fe.type === "PAGE_HIT" ? "hit" : "");
    box.textContent = `${fe.type}\n` + (fe.steps || []).join("\n");
  }

  el("rep-tbody").innerHTML = s.replacement_comparison
    .map(
      (r) => `<tr>
      <td>${r.algorithm}</td><td>${r.hits}</td><td>${r.faults}</td>
      <td>${r.hit_rate}</td><td>${r.fault_rate}</td></tr>`
    )
    .join("");

  const raid = s.raid;
  el("raid-meta").textContent =
    `${raid.level} · ${raid.num_disks} disks · R${raid.reads}/W${raid.writes} · ` +
    `available=${raid.data_available ? "YES" : "NO"} · util ${raid.storage_utilisation}%`;

  el("raid-disks").innerHTML = raid.disks
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
    .join("");

  const re = raid.last_event;
  const rb = el("raid-event");
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

  el("raid-cmp").innerHTML = raid.comparison
    .map(
      (c) => `<tr>
      <td>${c.level}</td><td>${c.read}</td><td>${c.write}</td>
      <td>${c.efficiency}</td><td>${c.fault_tolerance}</td><td>${c.disks_required}</td>
    </tr>`
    )
    .join("");

  const met = s.metrics;
  el("metrics").innerHTML = [
    ["CPU %", met.cpu_utilisation],
    ["Wait", met.average_waiting_time],
    ["TAT", met.average_turnaround_time],
    ["Resp", met.average_response_time],
    ["Done", met.completed_count],
    ["RAID %", raid.storage_utilisation],
  ]
    .map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`)
    .join("");

  el("log").textContent = (s.event_log || []).join("\n");
}

async function refresh() {
  render(await api("/api/state"));
}

async function applyConfig() {
  render(
    await api("/api/configure", "POST", {
      algorithm: el("algorithm").value,
      quantum: Number(el("quantum").value),
      ram_size_kb: Number(el("ram").value),
      page_size_kb: Number(el("page").value),
      virtual_size_kb: Number(el("virtual").value),
      replacement: el("replacement").value,
      raid_level: el("raid").value,
      num_disks: Number(el("disks").value),
    })
  );
}

function syncControlsFromState(s) {
  if (!s) return;
  el("algorithm").value = s.scheduler.algorithm;
  el("quantum").value = s.scheduler.quantum;
  el("ram").value = s.memory.ram_size_kb;
  el("page").value = s.memory.page_size_kb;
  el("virtual").value = s.memory.virtual_size_kb;
  el("replacement").value = s.memory.replacement;
  el("raid").value = s.raid.level;
  el("disks").value = s.raid.num_disks;
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

function bindTabs() {
  const tabs = document.querySelectorAll(".tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".monitor").forEach((m) => m.classList.remove("active"));
      tab.classList.add("active");
      el(`tab-${tab.dataset.tab}`).classList.add("active");
    });
  });
}

el("btn-generate").onclick = async () => {
  pauseAuto();
  const s = await api("/api/generate-processes", "POST");
  syncControlsFromState(s);
  render(s);
};
el("btn-demo").onclick = async () => {
  pauseAuto();
  const s = await api("/api/demo", "POST");
  syncControlsFromState(s);
  render(s);
};
el("btn-step").onclick = async () => render(await api("/api/step", "POST"));
el("btn-start").onclick = () => startAuto();
el("btn-pause").onclick = () => pauseAuto();
el("btn-run20").onclick = async () => render(await api("/api/run", "POST", { steps: 20 }));
el("btn-reset").onclick = async () => {
  pauseAuto();
  const s = await api("/api/reset", "POST");
  syncControlsFromState(s);
  render(s);
};
el("btn-apply").onclick = () => applyConfig();
el("btn-fail").onclick = async () =>
  render(await api("/api/fail-disk", "POST", { disk_id: Number(el("fail-id").value) }));
el("btn-recover").onclick = async () =>
  render(await api("/api/recover-disk", "POST", { disk_id: Number(el("fail-id").value) }));

bindTabs();
refresh().then(() => syncControlsFromState(state));
