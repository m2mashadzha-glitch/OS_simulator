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

function render(s) {
  state = s;
  el("sim-time").textContent = s.time;

  // Processes
  el("process-tbody").innerHTML = s.processes
    .map(
      (p) => `<tr>
      <td>${p.pid}</td><td>${p.arrival}</td><td>${p.burst}</td><td>${p.remaining}</td>
      <td>${p.priority}</td><td>${p.size_kb} KB</td><td>${p.num_pages}</td>
      <td><strong>${p.status}</strong></td></tr>`
    )
    .join("");

  // CPU
  if (s.running) {
    el("cpu-panel").innerHTML = `Running: ${s.running.pid}<br/>Burst: ${s.running.burst}<br/>Remaining: ${s.running.remaining}`;
  } else {
    el("cpu-panel").textContent = "CPU Idle";
  }
  el("sched-info").textContent = `Algorithm: ${s.scheduler.algorithm} · Quantum: ${s.scheduler.quantum}`;

  el("ready-queue").innerHTML = s.ready.length
    ? s.ready.map((p) => `<span class="chip">${p.pid}</span>`).join("")
    : `<span class="muted">Empty</span>`;
  el("completed").innerHTML = s.completed.length
    ? s.completed.map((p) => `<span class="chip">${p.pid}</span>`).join("")
    : `<span class="muted">None yet</span>`;

  el("gantt").innerHTML = s.gantt
    .map((g) => {
      const cls = g.pid === "IDLE" ? "idle" : "run";
      return `<span class="${cls}" title="t=${g.time}">${g.pid}</span>`;
    })
    .join("");

  // Memory
  const m = s.memory;
  el("mem-meta").textContent =
    `RAM ${m.ram_size_kb} KB · Page ${m.page_size_kb} KB · ${m.num_frames} frames · ` +
    `Virtual ${m.virtual_size_kb} KB (${m.num_virtual_pages} pages) · Replacement ${m.replacement}`;

  el("frames").innerHTML = Object.entries(m.frames)
    .map(([id, f]) => {
      if (f.free) return `<div class="frame free">Frame ${id}<br/>FREE</div>`;
      return `<div class="frame used">Frame ${id}<br/>${f.pid}-Page ${f.page}</div>`;
    })
    .join("");

  const rows = [];
  for (const [pid, entries] of Object.entries(m.page_tables)) {
    for (const e of entries) {
      rows.push(`<tr>
        <td>${pid}</td><td>${e.page}</td><td>${e.frame ?? "-"}</td>
        <td>${e.valid ? 1 : 0}</td><td>${e.dirty ? 1 : 0}</td><td>${e.location}</td>
      </tr>`);
    }
  }
  el("pt-tbody").innerHTML = rows.join("") || `<tr><td colspan="6">No page tables yet</td></tr>`;

  // VM
  el("vm-stats").innerHTML = [
    ["Page hits", m.page_hits],
    ["Page faults", m.page_faults],
    ["Hit rate", `${m.hit_rate}%`],
    ["Fault rate", `${m.fault_rate}%`],
    ["Replacements", m.replacements],
    ["Transfers", m.transfers],
    ["Mem util", `${m.memory_utilisation}%`],
  ]
    .map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`)
    .join("");

  const fe = m.last_event;
  const box = el("fault-box");
  if (!fe) {
    box.className = "fault-box";
    box.textContent = "No memory event yet. Step the simulation to see hits/faults.";
  } else {
    box.className = "fault-box " + (fe.type === "PAGE_HIT" ? "hit" : "");
    box.textContent = `${fe.type}\n` + (fe.steps || []).join("\n");
  }

  el("rep-tbody").innerHTML = s.replacement_comparison
    .map(
      (r) => `<tr>
      <td>${r.algorithm}</td><td>${r.hits}</td><td>${r.faults}</td>
      <td>${r.hit_rate}%</td><td>${r.fault_rate}%</td></tr>`
    )
    .join("");

  // RAID
  const raid = s.raid;
  el("raid-meta").textContent =
    `${raid.level} · ${raid.num_disks} disks · reads ${raid.reads} · writes ${raid.writes} · ` +
    `data available: ${raid.data_available ? "YES" : "NO"}`;

  el("raid-disks").innerHTML = raid.disks
    .map((d) => {
      const blocks = d.blocks
        .map((b, i) => (b ? `${i}:${b}` : null))
        .filter(Boolean)
        .slice(0, 12)
        .join("\n");
      return `<div class="disk ${d.failed ? "failed" : ""}">
        <h4>Disk ${d.disk_id} · ${d.status}</h4>
        <pre>${blocks || "(empty)"}</pre>
      </div>`;
    })
    .join("");

  const re = raid.last_event;
  const rb = el("raid-event");
  if (!re) {
    rb.className = "fault-box";
    rb.textContent = "RAID idle. Writes happen on page faults / demo load.";
  } else if (re.type === "DISK_FAILURE") {
    rb.className = "fault-box fail";
    rb.textContent =
      `${re.message}\nFailed Disk: Disk ${re.failed_disk}\n` +
      `Data Availability: ${re.data_available ? "YES" : "NO"}\nRecovery: ${re.recovery}`;
  } else {
    rb.className = "fault-box";
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

  // Metrics
  const met = s.metrics;
  el("metrics").innerHTML = [
    ["CPU util", `${met.cpu_utilisation}%`],
    ["Avg wait", met.average_waiting_time],
    ["Avg turnaround", met.average_turnaround_time],
    ["Avg response", met.average_response_time],
    ["Completed", met.completed_count],
    ["RAID util", `${raid.storage_utilisation}%`],
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

refresh().then(() => syncControlsFromState(state));
