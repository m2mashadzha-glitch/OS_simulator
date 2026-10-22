(() => {
  const $ = (id) => document.getElementById(id);

  let prevFrameLabels = {};
  let frameAnimTimer = null;

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
        const body = free ? "FREE" : `<span class="page-tag">${cur}</span>`;
        return `<div class="frame-cell ${free ? "free" : "used"} ${anim}" data-frame="${id}"><div class="fno">F${id}</div><div>${body}</div></div>`;
      })
      .join("");

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
      }
    }
  }

  function syncRamFromFrames() {
    const frames = Math.max(1, Number($("framesInput").value) || 1);
    const frameSize = Math.max(1, Number($("frameSizeInput").value) || 1);
    $("ramInput").value = frames * frameSize;
  }

  function schemePayload() {
    const scheme = $("schemeSelect").value;
    const page = Math.max(1, Number($("pageInput").value) || 1);
    const frameSize = Math.max(1, Number($("frameSizeInput").value) || 1);
    const frames = Math.max(1, Number($("framesInput").value) || 1);
    if (scheme === "Paging") {
      syncRamFromFrames();
    }
    return {
      memory_scheme: scheme,
      paging_mode: $("pagingModeSelect").value,
      ram_size_kb: Number($("ramInput").value),
      page_size_kb: page,
      frame_size_kb: frameSize,
      virtual_memory_kb: Number($("virtInput").value),
      frame_count: scheme === "Paging" ? frames : null,
    };
  }

  function renderCompare(state) {
    const runs = (state.scheme_comparison && state.scheme_comparison.runs) || {};
    const paging = runs.Paging;
    const seg = runs.Segmentation;
    if (!paging && !seg) {
      $("schemeCompare").innerHTML = "";
      return;
    }
    const row = (label, a, b) =>
      `<tr><td>${label}</td><td>${a ?? "—"}</td><td>${b ?? "—"}</td></tr>`;
    $("schemeCompare").innerHTML = `
      <table>
        <thead>
          <tr><th>Metric</th><th>Paging</th><th>Segmentation</th></tr>
        </thead>
        <tbody>
          ${row("Faults", paging && paging.faults, seg && seg.faults)}
          ${row("Hits", paging && paging.hits, seg && seg.hits)}
          ${row("Fault rate %", paging && paging.fault_rate, seg && seg.fault_rate)}
          ${row("Memory use %", paging && paging.memory_utilisation, seg && seg.memory_utilisation)}
          ${row("Internal frag (KB)", paging && paging.internal_fragmentation_kb, seg && seg.internal_fragmentation_kb)}
          ${row("External frag (KB)", paging && paging.external_fragmentation_kb, seg && seg.external_fragmentation_kb)}
          ${row("External frag %", paging && paging.external_fragmentation_pct, seg && seg.external_fragmentation_pct)}
          ${row("Replacements", paging && paging.replacements, seg && seg.replacements)}
          ${row("Alloc failures", paging && paging.allocation_failures, seg && seg.allocation_failures)}
        </tbody>
      </table>`;
  }

  function anyResidentPages(pageTables) {
    return Object.values(pageTables || {}).some((rows) =>
      rows.some((row) => row.valid_bit === 1 || row.location === "RAM")
    );
  }

  function renderPageTables(pageTables, { historic } = {}) {
    const hint = historic
      ? `<p class="sim-hint" style="margin:0 0 8px;">Showing last residency snapshot (pages were released when processes finished). Step mid-run to watch live Valid/Frame updates.</p>`
      : "";
    const tables =
      Object.entries(pageTables || {})
        .map(([pid, rows]) => {
          const body = rows
            .map((row) => {
              const inRam = row.valid_bit === 1 || row.location === "RAM";
              const frame =
                row.frame ?? row.display_frame ?? row.last_frame ?? "—";
              const phys = row.physical_start_kb ?? "—";
              const loc = inRam
                ? "RAM"
                : row.last_frame != null || row.display_frame != null
                  ? "Disk (was framed)"
                  : row.location || "Disk";
              return `<tr class="${inRam ? "row-resident" : ""}">
              <td>pg${row.page}</td>
              <td>${row.logical_start_kb ?? "—"}</td>
              <td>${frame}</td>
              <td>${phys}</td>
              <td>${row.valid_bit}</td>
              <td>${row.dirty_bit}</td>
              <td>${loc}</td>
            </tr>`;
            })
            .join("");
          return `<h4 style="margin:8px 0 4px;">Process ${pid}</h4>
          <table class="page-table"><thead><tr>
            <th>pg</th><th>Logical KB</th><th>Frame</th><th>Physical KB</th><th>Valid</th><th>Dirty</th><th>Location</th>
          </tr></thead>
          <tbody>${body}</tbody></table>`;
        })
        .join("") || "<p style='color:#888'>No processes registered.</p>";
    $("pageTables").innerHTML = hint + tables;
  }

  function renderPaging(state, mem) {
    $("mapTitle").textContent = `Physical frames (RAM) — ${mem.frame_count} frames`;
    $("tableTitle").textContent = "Page tables";
    $("pageField").style.display = "";
    $("framesField").style.display = "";
    $("frameSizeField").style.display = "";
    $("pagingModeField").style.display = "";

    const m = mem.metrics;
    $("memMetrics").innerHTML = `
      <div class="metric"><div class="name">Scheme</div><div class="num">Paging</div></div>
      <div class="metric"><div class="name">Paging type</div><div class="num">${state.paging_mode || "Demand paging"}</div></div>
      <div class="metric"><div class="name">Frames</div><div class="num">${mem.frame_count}</div></div>
      <div class="metric"><div class="name">Frame size</div><div class="num">${mem.frame_size_kb}KB</div></div>
      <div class="metric"><div class="name">Page size</div><div class="num">${mem.page_size_kb}KB</div></div>
      <div class="metric"><div class="name">Page faults</div><div class="num">${m.page_faults}</div></div>
      <div class="metric"><div class="name">Page hits</div><div class="num">${m.page_hits}</div></div>
      <div class="metric"><div class="name">Fault rate</div><div class="num">${m.page_fault_rate}%</div></div>
      <div class="metric"><div class="name">Relocations</div><div class="num">${m.relocations ?? 0}</div></div>
      <div class="metric"><div class="name">Internal frag</div><div class="num">${m.internal_fragmentation_kb}KB</div></div>
      <div class="metric"><div class="name">Memory use</div><div class="num">${m.memory_utilisation}%</div></div>`;

    const liveTables = mem.page_tables || {};
    const map = state.last_memory_map;
    const useHistoric =
      !anyResidentPages(liveTables) &&
      map &&
      map.scheme === "Paging" &&
      map.page_tables;

    if (useHistoric && map.frames) {
      renderFrameTransfers(map.frames);
      $("mapTitle").textContent = `Physical frames (last residency @ t=${map.at_time}) — ${mem.frame_count} frames`;
    } else {
      renderFrameTransfers(mem.frames || []);
    }

    renderPageTables(useHistoric ? map.page_tables : liveTables, {
      historic: Boolean(useHistoric),
    });
  }

  function renderSegmentation(state, mem) {
    $("mapTitle").textContent = "Physical memory map (contiguous segments)";
    $("tableTitle").textContent = "Segment tables";
    $("pageField").style.display = "none";
    $("framesField").style.display = "none";
    $("frameSizeField").style.display = "none";
    $("pagingModeField").style.display = "none";
    prevFrameLabels = {};
    if ($("frameTransfer")) {
      $("frameTransfer").textContent = "Segment map (contiguous regions).";
    }

    const m = mem.metrics;
    $("memMetrics").innerHTML = `
      <div class="metric"><div class="name">Scheme</div><div class="num">Segmentation</div></div>
      <div class="metric"><div class="name">Seg faults</div><div class="num">${m.segment_faults ?? m.page_faults}</div></div>
      <div class="metric"><div class="name">Seg hits</div><div class="num">${m.segment_hits ?? m.page_hits}</div></div>
      <div class="metric"><div class="name">Fault rate</div><div class="num">${m.fault_rate ?? m.page_fault_rate}%</div></div>
      <div class="metric"><div class="name">External frag</div><div class="num">${m.external_fragmentation_kb}KB</div></div>
      <div class="metric"><div class="name">Holes</div><div class="num">${m.free_holes}</div></div>
      <div class="metric"><div class="name">Relocations</div><div class="num">${m.relocations ?? 0}</div></div>
      <div class="metric"><div class="name">Memory use</div><div class="num">${m.memory_utilisation}%</div></div>`;

    $("frameGrid").innerHTML = (mem.regions || [])
      .map((region) => {
        const free = region.free;
        return `<div class="frame-cell ${free ? "free" : "used"}">
          <div class="fno">${region.start}–${region.start + region.size}KB</div>
          <div>${region.label} (${region.size}KB)</div>
        </div>`;
      })
      .join("") || "<p style='color:#888'>Empty memory map.</p>";

    $("pageTables").innerHTML =
      Object.entries(mem.segment_tables || {})
        .map(([pid, rows]) => {
          const body = rows
            .map(
              (row) => `<tr>
              <td>${row.segment}</td>
              <td>${row.name}</td>
              <td>${row.size_kb}</td>
              <td>${row.base ?? "—"}</td>
              <td>${row.limit ?? "—"}</td>
              <td>${row.valid_bit}</td>
              <td>${row.location}</td>
            </tr>`
            )
            .join("");
          return `<h4 style="margin:8px 0 4px;">Process ${pid}</h4>
          <table class="page-table"><thead><tr>
            <th>#</th><th>Name</th><th>Size</th><th>Base</th><th>Limit</th><th>Valid</th><th>Location</th>
          </tr></thead><tbody>${body}</tbody></table>`;
        })
        .join("") || "<p style='color:#888'>No processes registered.</p>";
  }

  function render(state) {
    const mem = state.memory;
    const scheme = state.memory_scheme || "Paging";
    $("schemeSelect").value = scheme;
    if (state.paging_mode) $("pagingModeSelect").value = state.paging_mode;
    const frames = mem.frame_count || state.physical_frames || 0;
    $("timeBadge").textContent = `Frames: ${frames} · Time: ${state.cpu.current_time} · ${scheme}`;

    $("ramInput").value = mem.ram_size_kb;
    if (mem.page_size_kb != null) $("pageInput").value = mem.page_size_kb;
    if (mem.frame_size_kb != null) $("frameSizeInput").value = mem.frame_size_kb;
    if (scheme === "Paging") {
      const fsz = mem.frame_size_kb || mem.page_size_kb || 4;
      $("framesInput").value =
        mem.frame_count || Math.max(1, Math.floor(mem.ram_size_kb / fsz));
    }
    $("virtInput").value = state.virtual_memory_kb;

    if (scheme === "Segmentation") {
      renderSegmentation(state, mem);
    } else {
      renderPaging(state, mem);
    }
    renderCompare(state);

    const event = state.last_memory_event;
    const reloc = (event && event.relocation) || mem.last_translation;
    if (!reloc) {
      $("relocBox").textContent =
        "No translation yet — Step a running process to apply relocation (logical → physical).";
    } else {
      $("relocBox").innerHTML = [
        `<div><span class="t">${reloc.scheme || scheme}</span>${reloc.formula}</div>`,
        `<div>logical ${reloc.logical_address_kb}KB -&gt; physical ${reloc.physical_address_kb ?? "—"}KB</div>`,
      ].join("");
    }

    if (!event) {
      $("faultSteps").textContent =
        "No memory access yet — press Step (uses the reference string).";
    } else {
      $("faultSteps").innerHTML = [
        `<div><span class="t">${event.result}</span>${event.message}</div>`,
        ...(event.steps || []).map((step) => `<div>${step}</div>`),
      ].join("");
    }
  }

  const { apply } = window.HpcUi.bindGlobalControls({ onState: render });

  $("btnRun").onclick = () => apply("/api/run-trace", { method: "POST" });
  $("btnApplyMem").onclick = () =>
    apply("/api/memory/config", {
      method: "POST",
      body: JSON.stringify(schemePayload()),
    });
  $("schemeSelect").onchange = () =>
    apply("/api/memory/config", {
      method: "POST",
      body: JSON.stringify(schemePayload()),
    });
  $("framesInput").addEventListener("input", syncRamFromFrames);
  $("frameSizeInput").addEventListener("input", syncRamFromFrames);

  window.HpcUi.api("/api/state").then(render);
})();
