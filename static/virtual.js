(() => {
  const $ = (id) => document.getElementById(id);

  function render(state) {
    $("timeBadge").textContent = `Time: ${state.cpu.current_time} · ref ${state.reference_index}`;
    $("algoSelect").value =
      state.replacement_algorithm === "OPT" ? "Optimal" : state.replacement_algorithm;
    $("refs").textContent = state.page_reference_string.join(", ");
    $("refsInput").value = state.page_reference_string.join(", ");

    const vm = state.dashboard.virtual_memory;
    const mem = state.memory.metrics;
    $("vmMetrics").innerHTML = `
      <div class="metric"><div class="name">Pages in RAM</div><div class="num">${vm.pages_in_ram}</div></div>
      <div class="metric"><div class="name">Pages on disk</div><div class="num">${vm.pages_on_secondary_storage}</div></div>
      <div class="metric"><div class="name">Transfers</div><div class="num">${vm.page_transfer_count}</div></div>
      <div class="metric"><div class="name">Replacements</div><div class="num">${vm.replacement_count}</div></div>
      <div class="metric"><div class="name">Hit rate</div><div class="num">${mem.page_hit_rate}%</div></div>`;
  }

  async function showComparison() {
    const data = await window.HpcUi.api("/api/memory/compare-replacement");
    $("compareTable").innerHTML = `
      <table>
        <thead><tr><th>Algorithm</th><th>Faults</th><th>Hits</th><th>Fault rate</th><th>Hit rate</th></tr></thead>
        <tbody>
          ${data.results
            .map(
              (row) => `<tr>
                <td>${row.algorithm}</td>
                <td>${row.page_faults}</td>
                <td>${row.page_hits}</td>
                <td>${row.fault_rate}%</td>
                <td>${row.hit_rate}%</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
      <p style="color:#555;font-size:12px;margin-top:6px;">
        Same reference string, ${data.frame_count} frames. Optimal is the theoretical lower bound on faults.
      </p>`;

    const focus = data.results[0];
    $("walkthrough").innerHTML = `
      <table>
        <thead><tr><th>Ref</th><th>Frames</th><th>Fault?</th></tr></thead>
        <tbody>
          ${focus.steps
            .map(
              (step) => `<tr>
                <td>${step.reference}</td>
                <td>${step.frames.map((f) => (f == null ? "-" : f)).join(" | ")}</td>
                <td>${step.fault ? "Yes" : "No"}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  const { apply } = window.HpcUi.bindGlobalControls({ onState: render });
  $("btnRun").onclick = () => apply("/api/run-trace", { method: "POST" });
  $("btnApplyAlgo").onclick = () =>
    apply("/api/memory/replacement", {
      method: "POST",
      body: JSON.stringify({ algorithm: $("algoSelect").value }),
    });
  $("btnApplyRefs").onclick = () => {
    const refs = $("refsInput")
      .value.split(",")
      .map((part) => Number(part.trim()))
      .filter((n) => !Number.isNaN(n));
    apply("/api/memory/references", {
      method: "POST",
      body: JSON.stringify({ references: refs }),
    });
  };
  $("btnCompare").onclick = () => showComparison().catch((error) => alert(error.message));

  window.HpcUi.api("/api/state").then(async (state) => {
    render(state);
    await showComparison();
  });
})();
