(() => {
  const $ = (id) => document.getElementById(id);

  function isParity(label) {
    return typeof label === "string" && /^(P|Q|Par)\(/.test(label);
  }

  function render(state) {
    const raid = state.raid;
    $("raidLevel").value = raid.level;
    $("diskCount").value = raid.disk_count;
    $("availBadge").textContent = `Data available: ${raid.data_available ? "YES" : "NO"}`;
    $("layoutSummary").textContent = raid.layout_summary || "";
    $("raidEvent").textContent = raid.last_event || "";
    const logical = raid.logical_blocks || [];
    $("logicalBlocks").textContent = logical.length
      ? `Stored process pages (${logical.length}): ${logical.join(", ")}`
      : "No process pages stored yet — apply processes and run a simulation.";

    $("diskGrid").innerHTML = raid.disks
      .map((disk) => {
        const failed = disk.status === "FAILED";
        const blocks = (disk.blocks || [])
          .map((b) => {
            const cls = isParity(b) ? "block parity" : "block data";
            return `<span class="${cls}">${b}</span>`;
          })
          .join("");
        return `<div class="disk-card ${failed ? "failed" : "online"}">
          <div class="fno">${disk.name} — ${disk.status}</div>
          <div class="blocks">${blocks || "<span class='empty'>empty</span>"}</div>
        </div>`;
      })
      .join("");

    $("compare").innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Level</th><th>Min disks</th><th>Read</th><th>Write</th>
            <th>Efficiency</th><th>Fault tolerance</th><th>Recovery</th>
          </tr>
        </thead>
        <tbody>
          ${raid.all_levels
            .map(
              (row) => `<tr>
                <td>${row.level}</td>
                <td>${row.min_disks}</td>
                <td>${row.read_performance}</td>
                <td>${row.write_performance}</td>
                <td>${row.storage_efficiency}</td>
                <td>${row.fault_tolerance}</td>
                <td>${row.recovery}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>`;

    const m = raid.metrics;
    $("raidMetrics").innerHTML = `
      <div class="metric"><div class="name">Reads</div><div class="num">${m.read_operations}</div></div>
      <div class="metric"><div class="name">Writes</div><div class="num">${m.write_operations}</div></div>
      <div class="metric"><div class="name">Logical pages</div><div class="num">${m.logical_blocks ?? logical.length}</div></div>
      <div class="metric"><div class="name">Failed disks</div><div class="num">${m.failed_disks}</div></div>
      <div class="metric"><div class="name">Recoveries</div><div class="num">${m.recovery_operations}</div></div>
      <div class="metric"><div class="name">Storage online</div><div class="num">${m.storage_utilisation}%</div></div>`;
  }

  async function apply(path, options) {
    try {
      render(await window.HpcUi.api(path, options));
    } catch (error) {
      alert(error.message);
    }
  }

  $("btnApplyRaid").onclick = () =>
    apply("/api/raid/config", {
      method: "POST",
      body: JSON.stringify({
        level: $("raidLevel").value,
        disk_count: Number($("diskCount").value),
      }),
    });
  $("btnFail").onclick = () =>
    apply("/api/raid/fail", {
      method: "POST",
      body: JSON.stringify({ disk_id: Number($("failDisk").value) }),
    });
  $("btnRecover").onclick = () => apply("/api/raid/recover", { method: "POST" });

  window.HpcUi.api("/api/state").then(render);
})();
