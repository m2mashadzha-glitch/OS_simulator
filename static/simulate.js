(() => {
  const $ = (id) => document.getElementById(id);

  const POLICY_BLURB = {
    FCFS: "Scheduler: FCFS (non-preemptive)",
    "Round Robin": "Scheduler: Round Robin (preemptive)",
    "Shortest Job First": "Scheduler: SJF (non-preemptive)",
    Priority: "Scheduler: Priority (non-preemptive)",
  };

  let lastEventKey = "";
  let animTimer = null;
  let prevFrameLabels = {};
  let frameAnimTimer = null;

  const toneFor = (processId) => {
    const n = Number(String(processId).replace(/\D/g, "")) || 1;
    return `tone-${(n - 1) % 6}`;
  };

  function cells(total, remaining, onClass, offClass) {
    const count = Math.max(total, 0);
    const rem = Math.max(remaining, 0);
    const done = count - rem;
    let html = "";
    for (let i = 0; i < done; i += 1) html += `<span class="cell ${offClass}"></span>`;
    for (let i = 0; i < rem; i += 1) html += `<span class="cell ${onClass}"></span>`;
    return html || `<span class="cell ${offClass}"></span>`;
  }

  function processCard(process) {
    return `
      <div class="process-card ${toneFor(process.process_id)}">
        <div class="pid">PID ${String(process.process_id).replace(/\D/g, "") || process.process_id}</div>
        <div class="name">${process.process_id}</div>
        <div class="prio">prio ${process.priority}</div>
        <div class="job">${process.description || "research job"}</div>
        <div class="burst-grid">
          <div class="burst-row">
            <span>CPU</span>
            <div class="cells">${cells(process.burst_time, process.remaining_burst, "cpu-on", "cpu-off")}</div>
          </div>
          <div class="burst-row">
            <span>MEM</span>
            <div class="cells">${cells(process.number_of_pages || 1, process.number_of_pages || 1, "mem-on", "mem-off")}</div>
          </div>
        </div>
      </div>`;
  }

  function isParity(label) {
    return typeof label === "string" && /^(P|Q|Par)\(/.test(label);
  }

  function clearHighlights() {
    ["nodeRaid", "nodeVirt", "nodeMem", "nodeCpu"].forEach((id) => {
      $(id).classList.remove("active", "fault", "hit");
    });
  }

  function placeTokenOn(nodeId) {
    const pipeline = $("pagePipeline");
    const token = $("pageToken");
    const node = $(nodeId);
    if (!pipeline || !token || !node) return;
    const pRect = pipeline.getBoundingClientRect();
    const nRect = node.getBoundingClientRect();
    const left = nRect.left - pRect.left + nRect.width / 2 - token.offsetWidth / 2;
    const top = nRect.top - pRect.top + nRect.height / 2 - token.offsetHeight / 2;
    token.style.left = `${Math.max(0, left)}px`;
    token.style.top = `${Math.max(0, top)}px`;
  }

  function animatePageMove(event) {
    if (!event) return;
    const key = `${event.result}|${event.message}|${event.time || ""}`;
    if (key === lastEventKey) return;
    lastEventKey = key;

    if (animTimer) {
      clearTimeout(animTimer);
      animTimer = null;
    }
    clearHighlights();

    const token = $("pageToken");
    const label =
      event.scheme === "Segmentation"
        ? `${event.process_id}:${event.name || "seg"}`
        : `${event.process_id}:pg${event.page ?? "?"}`;
    token.hidden = false;
    token.textContent = label;
    token.className = `page-token ${event.result === "FAULT" ? "fault" : "hit"}`;

    const steps =
      event.result === "FAULT"
        ? [
            { node: "nodeRaid", cls: "fault", status: `FAULT — fetch ${label} from RAID / disk` },
            { node: "nodeVirt", cls: "fault", status: `Load ${label} via virtual memory backing store` },
            { node: "nodeMem", cls: "fault", status: `Place ${label} into main memory frame` },
            { node: "nodeCpu", cls: "fault", status: `Resume CPU with ${label}` },
          ]
        : [
            { node: "nodeMem", cls: "hit", status: `HIT — ${label} already in main memory` },
            { node: "nodeCpu", cls: "hit", status: `Deliver ${label} to CPU` },
          ];

    let i = 0;
    const tick = () => {
      clearHighlights();
      const step = steps[i];
      if (!step) {
        $("pipelineStatus").textContent = event.message;
        return;
      }
      const el = $(step.node);
      el.classList.add("active", step.cls);
      $("pipelineStatus").textContent = step.status;
      placeTokenOn(step.node);
      i += 1;
      animTimer = setTimeout(tick, 1100);
    };
    // Position token before first paint
    requestAnimationFrame(() => {
      placeTokenOn(steps[0].node);
      tick();
    });
  }

  function renderVirtual(state, mem) {
    const dash = (state.dashboard && state.dashboard.virtual_memory) || {};
    const m = mem.metrics || {};
    const inRam = dash.pages_in_ram ?? m.pages_in_ram ?? 0;
    const onDisk = dash.pages_on_secondary_storage ?? m.pages_on_disk ?? 0;
    const total = Math.max(1, inRam + onDisk);
    const virtPages = state.virtual_pages ?? 0;
    const frames = state.physical_frames ?? 0;

    $("vmMetrics").innerHTML = `
      <div class="metric"><div class="name">Virtual size</div><div class="num">${state.virtual_memory_kb}KB</div></div>
      <div class="metric"><div class="name">Virtual pages</div><div class="num">${virtPages}</div></div>
      <div class="metric"><div class="name">Frames</div><div class="num">${frames}</div></div>
      <div class="metric"><div class="name">In RAM</div><div class="num">${inRam}</div></div>
      <div class="metric"><div class="name">On disk</div><div class="num">${onDisk}</div></div>
      <div class="metric"><div class="name">Transfers</div><div class="num">${dash.page_transfer_count ?? m.pages_transferred ?? 0}</div></div>`;

    $("vmRamFill").style.width = `${(inRam / total) * 100}%`;
    $("vmDiskFill").style.width = `${(onDisk / total) * 100}%`;
    $("vmRamVal").textContent = inRam;
    $("vmDiskVal").textContent = onDisk;

    const refs = state.page_reference_string || [];
    const idx = state.reference_index || 0;
    $("vmRefs").innerHTML = refs.length
      ? refs
          .map((r, i) => `<span class="${i === idx ? "ref-now" : i < idx ? "ref-done" : ""}">${r}</span>`)
          .join(" ")
      : "No reference string";
    $("vmAlgoLine").textContent = `Replacement: ${state.replacement_algorithm || "FIFO"} · scheme ${state.memory_scheme || "Paging"}`;
    $("pipeVirtSub").textContent = `${state.virtual_memory_kb}KB virt`;
    $("pipeMemSub").textContent = `${inRam} in RAM / ${onDisk} disk`;
  }

  function render(state) {
    const cpu = state.cpu || {};
    const processes = Array.isArray(cpu.processes) ? cpu.processes : [];
    const readyQueue = Array.isArray(cpu.ready_queue) ? cpu.ready_queue : [];
    const gantt = Array.isArray(cpu.gantt) ? cpu.gantt : [];
    const metrics = cpu.metrics || {};
    const mem = state.memory || {};
    const raid = state.raid || {};
    const scheme = state.memory_scheme || "Paging";

    $("timeBadge").textContent = `Time: ${cpu.current_time ?? 0} · refs ${state.reference_index ?? 0}/${(state.page_reference_string || []).length} · ${scheme}`;
    $("algoLine").textContent = POLICY_BLURB[cpu.scheduling_policy] || cpu.scheduling_policy || "";
    $("schemeLabel").textContent = scheme;
    $("raidLabel").textContent = raid.level || "RAID";
    $("pipeRaidSub").textContent = raid.level || "RAID";
    const processors = (cpu.cpu && cpu.cpu.processors) || [];
    const running = cpu.cpu && cpu.cpu.running;
    const cpuCount = cpu.processor_count || processors.length || 1;
    $("cpuCountLabel").textContent = String(cpuCount);
    const busyIds = processors
      .filter((slot) => slot.running)
      .map((slot) => `CPU${slot.cpu_id}:${slot.running.process_id}`);
    if ($("cpuRunLine")) {
      $("cpuRunLine").textContent = busyIds.length
        ? `Running now — ${busyIds.join(" · ")} · ${readyQueue.length} waiting in Ready`
        : readyQueue.length
          ? `${readyQueue.length} ready — waiting to dispatch`
          : "No processors busy.";
    }
    $("pipeCpuSub").textContent = busyIds.length
      ? `${busyIds.map((s) => s.split(":")[1]).join(", ")} (${cpuCount} CPU)`
      : `idle (${cpuCount} CPU)`;

    const total = metrics.total_processes || processes.length;
    if (!total) {
      $("simHint").textContent =
        "No processes loaded — open Processes, add jobs, Apply processes, then return here to simulate.";
    } else {
      $("simHint").textContent = `${total} process(es) loaded. Watch page movement as Step/Play runs. Reset clears everything to defaults.`;
    }

    const memM = mem.metrics || {};
    const framesUsed = memM.pages_in_ram ?? 0;
    const framesTotal = memM.frames_total ?? state.physical_frames ?? 0;
    $("topMetrics").innerHTML = `
      <div class="metric"><div class="name">CPU use</div><div class="num">${metrics.cpu_utilisation ?? 0}%</div></div>
      <div class="metric"><div class="name">Avg wait</div><div class="num">${metrics.average_waiting_time ?? 0}</div></div>
      <div class="metric"><div class="name">Completed</div><div class="num">${metrics.completed_count ?? 0}/${total}</div></div>
      <div class="metric"><div class="name">Mem use</div><div class="num">${memM.memory_utilisation ?? 0}%</div></div>
      <div class="metric"><div class="name">Frames</div><div class="num">${framesUsed}/${framesTotal}</div></div>
      <div class="metric"><div class="name">Mem faults</div><div class="num">${memM.page_faults ?? 0}</div></div>
      <div class="metric"><div class="name">RAID writes</div><div class="num">${(raid.metrics && raid.metrics.write_operations) ?? 0}</div></div>`;

    renderVirtual(state, mem);

    const byId = Object.fromEntries(processes.map((p) => [p.process_id, p]));
    // Head of queue on the left (FCFS dequeue order).
    const readyVisual = readyQueue.map((id) => byId[id]).filter(Boolean);
    if (!readyVisual.length) {
      $("readyTrack").innerHTML = '<div class="ready-empty">No jobs in ready queue</div>';
    } else {
      const parts = [];
      readyVisual.forEach((process, index) => {
        parts.push(processCard(process));
        if (index < readyVisual.length - 1) parts.push('<div class="flow-arrow">→</div>');
      });
      $("readyTrack").innerHTML = parts.join("");
    }

    const grid = $("processorGrid");
    if (processors.length) {
      grid.innerHTML = processors
        .map((slot) => {
          if (!slot.running) {
            return `<div class="processor-box idle">CPU${slot.cpu_id}<span class="cpu-idle-tag">Idle</span></div>`;
          }
          return `<div class="processor-box busy"><div class="section-title">CPU${slot.cpu_id} <span class="cpu-busy-tag">Busy</span></div><div class="running-card">${processCard(slot.running)}</div></div>`;
        })
        .join("");
    } else if (!running) {
      grid.innerHTML = `<div class="processor-box idle">CPU1<span class="cpu-idle-tag">Idle</span></div>`;
    } else {
      grid.innerHTML = `<div class="processor-box busy"><div class="section-title">CPU1 <span class="cpu-busy-tag">Busy</span></div><div class="running-card">${processCard(running)}</div></div>`;
    }

    const completed = processes.filter((p) => p.status === "Terminated");
    $("completedTable").innerHTML = completed.length
      ? completed
          .map(
            (p) =>
              `<tr><td>${p.process_id}</td><td>${p.turnaround_time}</td><td>${p.waiting_time}</td></tr>`
          )
          .join("")
      : `<tr><td colspan="3" style="color:#888;">None yet</td></tr>`;

    $("gantt").innerHTML = gantt.length
      ? gantt
          .map((slice) => {
            const idle = slice.process_id == null;
            return `<div class="gantt-slice ${idle ? "idle" : ""}" style="flex:${Math.max(slice.duration, 1)}"><strong>${slice.label}</strong><span>${slice.start_time}–${slice.end_time}</span></div>`;
          })
          .join("")
      : `<div class="gantt-slice idle">No CPU activity yet</div>`;

    if (scheme === "Segmentation") {
      $("frameGrid").innerHTML = (mem.regions || [])
        .map((region) => {
          const free = region.free;
          return `<div class="frame-cell ${free ? "free" : "used"}"><div class="fno">${region.start}–${region.start + region.size}KB</div><div>${region.label}</div></div>`;
        })
        .join("") || "<div class='frame-cell free'>empty</div>";
      if ($("frameTransfer")) {
        $("frameTransfer").textContent = "Segment map (contiguous regions).";
      }
      prevFrameLabels = {};
    } else {
      renderFrameTransfers(mem.frames || []);
    }

    const event = state.last_memory_event;
    const reloc = (event && event.relocation) || mem.last_translation;
    if (!reloc) {
      $("relocBox").textContent = "No translation yet.";
    } else {
      $("relocBox").innerHTML = [
        `<div><span class="t">reloc</span>${reloc.formula}</div>`,
        `<div>logical ${reloc.logical_address_kb}KB -&gt; physical ${reloc.physical_address_kb ?? "—"}KB</div>`,
      ].join("");
    }
    if (!event) {
      $("memEvent").textContent = "No memory access yet.";
    } else {
      $("memEvent").innerHTML = [
        `<div><span class="t">${event.result}</span>${event.message}</div>`,
        ...(event.steps || []).slice(0, 4).map((step) => `<div>${step}</div>`),
      ].join("");
      animatePageMove(event);
    }

    $("diskGrid").innerHTML = (raid.disks || [])
      .map((disk) => {
        const failed = disk.status === "FAILED";
        const blocks = (disk.blocks || [])
          .slice(0, 8)
          .map((b) => `<span class="block ${isParity(b) ? "parity" : "data"}">${b}</span>`)
          .join("");
        return `<div class="disk-card ${failed ? "failed" : "online"}"><div class="fno">${disk.name}</div><div class="blocks">${blocks || "<span class='empty'>empty</span>"}</div></div>`;
      })
      .join("");
    $("raidEvent").textContent = raid.last_event || "";

    const log = state.kernel_log || cpu.event_log || [];
    $("eventLog").innerHTML = [...log]
      .reverse()
      .slice(0, 40)
      .map((e) => `<div><span class="t">t=${e.time}</span>${e.message}</div>`)
      .join("") || "<div>No events yet.</div>";
  }

  function renderFrameTransfers(frames) {
    const transfers = [];
    const nextLabels = {};
    $("frameGrid").innerHTML = frames
      .map((frame) => {
        const id = frame.frame;
        const cur = frame.label || "FREE";
        const prev = prevFrameLabels[id];
        nextLabels[id] = cur;
        const free = cur === "FREE";
        let anim = "";
        if (prev != null && prev !== cur) {
          if (prev === "FREE" && !free) {
            anim = "page-in";
            transfers.push(`<span class="xfer-in">IN</span> ${cur} → F${id}`);
          } else if (!free && prev !== "FREE" && cur !== prev) {
            anim = "page-swap";
            transfers.push(
              `<span class="xfer-swap">SWAP</span> ${prev} out, ${cur} in → F${id}`
            );
          } else if (free && prev !== "FREE") {
            anim = "page-out";
            transfers.push(`<span class="xfer-out">OUT</span> ${prev} ← F${id}`);
          }
        }
        const body = free
          ? "FREE"
          : `<span class="page-tag">${cur}</span>`;
        return `<div class="frame-cell ${free ? "free" : "used"} ${anim}" data-frame="${id}"><div class="fno">F${id}</div><div>${body}</div></div>`;
      })
      .join("") || "<div class='frame-cell free'>no frames</div>";

    prevFrameLabels = nextLabels;
    const log = $("frameTransfer");
    if (log) {
      if (transfers.length) {
        log.innerHTML = transfers.join(" · ");
        if (frameAnimTimer) clearTimeout(frameAnimTimer);
        frameAnimTimer = setTimeout(() => {
          document.querySelectorAll("#frameGrid .frame-cell").forEach((el) => {
            el.classList.remove("page-in", "page-out", "page-swap");
          });
        }, 1200);
      } else if (!Object.keys(nextLabels).length) {
        log.textContent = "Pages entering / leaving frames appear here.";
      }
    }
  }

  const { apply, stopAuto } = window.HpcUi.bindGlobalControls({ onState: render });

  $("btnResetAll").onclick = async () => {
    stopAuto();
    if (!confirm("Reset everything to defaults? This clears all applied processes.")) return;
    lastEventKey = "";
    prevFrameLabels = {};
    clearHighlights();
    $("pageToken").hidden = true;
    $("pipelineStatus").textContent = "Waiting for a memory access…";
    if ($("frameTransfer")) {
      $("frameTransfer").textContent = "Pages entering / leaving frames appear here.";
    }
    await apply("/api/reset-defaults", { method: "POST" });
  };

  window.HpcUi.api("/api/state").then(render);
})();
