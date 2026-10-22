(() => {
  const $ = (id) => document.getElementById(id);

  function metricHtml(entries) {
    return entries
      .map(
        ([name, value]) =>
          `<div class="metric"><div class="name">${name}</div><div class="num">${value}</div></div>`
      )
      .join("");
  }

  function render(state) {
    const last = state.last_run;
    const usingLast = Boolean(last && last.dashboard);
    const d = usingLast ? last.dashboard : state.dashboard;
    const scheme = usingLast
      ? last.memory_scheme
      : state.memory_scheme || (d.memory && d.memory.scheme) || "Paging";

    if ($("metricsSource")) {
      $("metricsSource").textContent = usingLast
        ? `Last completed run · t=${last.completed_at_time} · ${last.scheduling_policy} · ${scheme}`
        : "No completed run yet — showing live counters (Run a workload to freeze metrics).";
    }

    $("timeBadge").textContent = usingLast
      ? `Last run · t=${last.completed_at_time}`
      : `Time: ${state.cpu.current_time}`;

    $("cpuMetrics").innerHTML = metricHtml([
      ["CPU utilisation", `${d.cpu.cpu_utilisation}%`],
      ["Avg waiting", d.cpu.average_waiting_time],
      ["Avg turnaround", d.cpu.average_turnaround_time],
      ["Avg response", d.cpu.average_response_time],
      ["Completed", `${d.cpu.completed_count}/${d.cpu.total_processes}`],
    ]);

    const framesUsed = d.memory.pages_in_ram ?? 0;
    const framesTotal = d.memory.frames_total ?? d.virtual_memory.physical_frames ?? 0;
    const ramUsedKb = d.memory.ram_used_kb ?? 0;
    const ramTotalKb = d.memory.ram_size_kb ?? state.memory?.ram_size_kb ?? 0;
    const useLabel =
      d.memory.usage_basis === "peak_during_run" ? "Peak mem use" : "Memory use";
    const framesLabel =
      d.memory.usage_basis === "peak_during_run" ? "Peak frames" : "Frames used";
    const ramLabel =
      d.memory.usage_basis === "peak_during_run" ? "Peak RAM" : "RAM used";

    $("memMetrics").innerHTML = metricHtml([
      ["Scheme", d.memory.scheme || scheme],
      [useLabel, `${d.memory.memory_utilisation ?? 0}%`],
      [framesLabel, `${framesUsed}/${framesTotal}`],
      [ramLabel, `${ramUsedKb}/${ramTotalKb}KB`],
      ["Faults", d.memory.page_faults],
      ["Hits", d.memory.page_hits],
      ["Fault rate", `${d.memory.page_fault_rate}%`],
      ["Internal frag KB", d.memory.internal_fragmentation_kb ?? 0],
      ["External frag KB", d.memory.external_fragmentation_kb ?? 0],
    ]);
    $("vmMetrics").innerHTML = metricHtml([
      ["Pages in RAM", d.virtual_memory.pages_in_ram],
      ["Pages on disk", d.virtual_memory.pages_on_secondary_storage],
      ["Transfers", d.virtual_memory.page_transfer_count],
      ["Replacements", d.virtual_memory.replacement_count],
      ["Virtual pages", d.virtual_memory.virtual_pages],
      ["Physical frames", d.virtual_memory.physical_frames],
    ]);
    $("raidMetrics").innerHTML = metricHtml([
      ["Reads", d.raid.read_operations],
      ["Writes", d.raid.write_operations],
      ["Failed disks", d.raid.failed_disks],
      ["Recoveries", d.raid.recovery_operations],
      ["Storage online", `${d.raid.storage_utilisation}%`],
    ]);

    const log = usingLast ? last.kernel_log || [] : state.kernel_log || [];
    $("kernelLog").innerHTML = [...log]
      .reverse()
      .map((event) => `<div><span class="t">t=${event.time}</span>${event.message}</div>`)
      .join("") || "<div>No events yet.</div>";
  }

  const { apply } = window.HpcUi.bindGlobalControls({ onState: render });
  $("btnRun").onclick = () => apply("/api/run", { method: "POST" });
  window.HpcUi.api("/api/state").then(render);
})();
