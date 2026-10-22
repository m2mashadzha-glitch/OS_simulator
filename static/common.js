window.HpcUi = {
  async api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      const message = Array.isArray(detail.detail)
        ? detail.detail.map((item) => item.msg || JSON.stringify(item)).join("; ")
        : detail.detail || response.statusText;
      throw new Error(message);
    }
    return response.json();
  },

  bindGlobalControls({ onState }) {
    const $ = (id) => document.getElementById(id);
    let autoTimer = null;
    let playing = false;
    const stopAuto = () => {
      playing = false;
      if (autoTimer) {
        clearTimeout(autoTimer);
        clearInterval(autoTimer);
        autoTimer = null;
      }
    };

    const apply = async (path, options) => {
      try {
        const state = await this.api(path, options);
        onState(state);
        return state;
      } catch (error) {
        alert(error.message);
        return null;
      }
    };

    if ($("btnStep")) $("btnStep").onclick = () => apply("/api/step", { method: "POST" });
    if ($("btnPause"))
      $("btnPause").onclick = async () => {
        stopAuto();
        await apply("/api/pause", { method: "POST" });
      };
    if ($("btnStop"))
      $("btnStop").onclick = async () => {
        stopAuto();
        await apply("/api/reset", { method: "POST" });
      };
    if ($("btnRun"))
      $("btnRun").onclick = async () => {
        stopAuto();
        await apply("/api/run", { method: "POST" });
      };
    if ($("btnStart"))
      $("btnStart").onclick = async () => {
        stopAuto();
        await apply("/api/start", { method: "POST" });
        // Slider 1 = slow (~7s/step), 10 = faster (~1.2s/step)
        const stepDelay = () => {
          const level = Number(($("speedSlider") || {}).value || 1);
          return Math.max(1200, 7800 - level * 660);
        };
        playing = true;
        const tick = async () => {
          if (!playing) return;
          const state = await this.api("/api/step", { method: "POST" });
          if (!playing) return;
          onState(state);
          if (
            state.cpu.is_complete &&
            state.reference_index >= state.page_reference_string.length
          ) {
            stopAuto();
            await this.api("/api/pause", { method: "POST" });
            return;
          }
          autoTimer = setTimeout(tick, stepDelay());
        };
        autoTimer = setTimeout(tick, stepDelay());
      };

    return { apply, stopAuto };
  },
};
