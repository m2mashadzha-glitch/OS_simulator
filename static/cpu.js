(() => {
  const $ = (id) => document.getElementById(id);

  const POLICY_BLURB = {
    FCFS: "First Come First Served. Non-preemptive.",
    "Round Robin": "Round Robin. Preemptive time slices on the HPC CPU.",
    "Shortest Job First": "Shortest Job First. Non-preemptive, shortest remaining job next.",
    Priority: "Priority scheduling. Lower number = higher priority (non-preemptive).",
  };

  function setEditorMsg(text, isError = false) {
    const el = $("editorMsg");
    el.textContent = text;
    el.className = isError ? "editor-msg error" : "editor-msg";
  }

  function toProcessId(index, raw = "") {
    const digits = String(raw).replace(/\D/g, "");
    return `P${digits || index + 1}`;
  }

  function emptyRow(index) {
    return {
      process_id: `P${index + 1}`,
      description: "",
      arrival_time: index,
      burst_time: 5,
      priority: 1,
      process_size_kb: 8,
      memory_requirement_kb: 8,
    };
  }

  function renderEditorRows(rows) {
    $("processEditorBody").innerHTML = rows
      .map(
        (row, index) => `
      <tr data-index="${index}">
        <td><input data-field="process_id" value="${toProcessId(index, row.process_id)}" /></td>
        <td><input data-field="description" value="${row.description || ""}" /></td>
        <td><input class="num" type="number" min="0" data-field="arrival_time" value="${row.arrival_time}" /></td>
        <td><input class="num" type="number" min="1" data-field="burst_time" value="${row.burst_time}" /></td>
        <td><input class="num" type="number" min="1" data-field="priority" value="${row.priority}" /></td>
        <td><input class="num" type="number" min="1" data-field="process_size_kb" value="${row.process_size_kb}" /></td>
        <td><input class="num" type="number" min="1" data-field="memory_requirement_kb" value="${row.memory_requirement_kb}" /></td>
      </tr>`
      )
      .join("");
  }

  function readEditorRows() {
    return [...$("processEditorBody").querySelectorAll("tr")].map((tr, index) => {
      const get = (field) => tr.querySelector(`[data-field="${field}"]`).value;
      return {
        process_id: toProcessId(index, get("process_id")),
        description: get("description").trim(),
        arrival_time: Number(get("arrival_time")),
        burst_time: Number(get("burst_time")),
        priority: Number(get("priority")),
        process_size_kb: Number(get("process_size_kb")),
        memory_requirement_kb: Number(get("memory_requirement_kb")),
      };
    });
  }

  function fillEditorFromProcesses(processes) {
    const list = Array.isArray(processes) ? processes : [];
    const rows = list.map((p, index) => ({
      process_id: toProcessId(index, p.process_id),
      description: p.description || "",
      arrival_time: p.arrival_time,
      burst_time: p.burst_time,
      priority: p.priority,
      process_size_kb: p.process_size_kb,
      memory_requirement_kb: p.memory_requirement_kb ?? p.process_size_kb,
    }));
    renderEditorRows(rows.length ? rows : [emptyRow(0)]);
  }

  function renderApplied(processes) {
    const list = Array.isArray(processes) ? processes : [];
    $("appliedTable").innerHTML = list.length
      ? list
          .map(
            (p) => `<tr>
              <td>${p.process_id}</td>
              <td>${p.description || "—"}</td>
              <td>${p.arrival_time}</td>
              <td>${p.burst_time}</td>
              <td>${p.priority}</td>
              <td>${p.process_size_kb} KB</td>
              <td>${p.status}</td>
            </tr>`
          )
          .join("")
      : `<tr><td colspan="7" style="color:#888;">No processes applied yet.</td></tr>`;
  }

  function render(state) {
    const cpu = state.cpu || {};
    const processes = Array.isArray(cpu.processes) ? cpu.processes : [];
    const cpus = cpu.processor_count || 1;
    $("timeBadge").textContent = `${processes.length} process(es) · ${cpus} CPU(s)`;
    $("algoLine").textContent =
      `${POLICY_BLURB[cpu.scheduling_policy] || cpu.scheduling_policy || ""} · ${cpus} processor(s)`;
    if (cpu.scheduling_policy) $("policySelect").value = cpu.scheduling_policy;
    if (cpu.time_quantum != null) $("quantumInput").value = cpu.time_quantum;
    if ($("processorSelect") && cpu.processor_count != null) {
      $("processorSelect").value = String(cpu.processor_count);
    }
    renderApplied(processes);
  }

  $("btnAddProcess").addEventListener("click", () => {
    const rows = readEditorRows();
    rows.push(emptyRow(rows.length));
    renderEditorRows(rows);
    setEditorMsg(`Row added. ${rows.length} process(es) in editor.`);
  });

  $("btnRemoveProcess").addEventListener("click", () => {
    const rows = readEditorRows();
    if (rows.length <= 1) {
      setEditorMsg("Keep at least one process row.", true);
      return;
    }
    rows.pop();
    renderEditorRows(rows);
    setEditorMsg(`Removed last row. ${rows.length} process(es) left.`);
  });

  $("btnClearEditor").addEventListener("click", () => {
    renderEditorRows([emptyRow(0)]);
    setEditorMsg("Editor cleared.");
  });

  $("btnApplyProcesses").addEventListener("click", async () => {
    const processes = readEditorRows();
    for (const process of processes) {
      if (!process.process_id) {
        setEditorMsg("Every process needs a PID.", true);
        return;
      }
      if (
        Number.isNaN(process.arrival_time) ||
        Number.isNaN(process.burst_time) ||
        Number.isNaN(process.priority) ||
        Number.isNaN(process.process_size_kb) ||
        Number.isNaN(process.memory_requirement_kb)
      ) {
        setEditorMsg("All numeric fields must be valid numbers.", true);
        return;
      }
      if (process.burst_time < 1 || process.process_size_kb < 1 || process.memory_requirement_kb < 1) {
        setEditorMsg("Burst, size and memory must be at least 1.", true);
        return;
      }
    }
    const ids = processes.map((p) => p.process_id);
    if (new Set(ids).size !== ids.length) {
      setEditorMsg("Each PID must be unique.", true);
      return;
    }

    try {
      const state = await window.HpcUi.api("/api/workload/custom", {
        method: "POST",
        body: JSON.stringify({
          name: "Custom Research Workload",
          scenario: "User-defined research jobs on the HPC node",
          processes,
        }),
      });
      const applied = (state.cpu && state.cpu.processes) || [];
      fillEditorFromProcesses(applied);
      render(state);
      setEditorMsg(
        `Applied ${processes.length} process(es). Open Simulate to Play / Step / Run.`
      );
    } catch (error) {
      setEditorMsg(error.message, true);
    }
  });

  $("btnApplyScheduler").addEventListener("click", async () => {
    try {
      const state = await window.HpcUi.api("/api/scheduler", {
        method: "POST",
        body: JSON.stringify({
          policy: $("policySelect").value,
          time_quantum: Number($("quantumInput").value) || 4,
          processor_count: Number($("processorSelect").value) || 1,
        }),
      });
      render(state);
      setEditorMsg(
        `Scheduler set to ${$("policySelect").value} with ${$("processorSelect").value} CPU(s).`
      );
    } catch (error) {
      setEditorMsg(error.message, true);
    }
  });

  renderEditorRows([emptyRow(0)]);
  window.HpcUi.api("/api/state").then((state) => {
    const processes = (state.cpu && state.cpu.processes) || [];
    if (processes.length) fillEditorFromProcesses(processes);
    render(state);
  });
})();
