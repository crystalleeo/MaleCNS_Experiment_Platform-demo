(() => {
  const el = id => document.getElementById(id);

  const taskStage = el("taskStage");
  const fixation = el("fixation");
  const cue = el("cue");
  const stimulus = el("stimulus");
  const message = el("message");

  let sessionStartPerf = performance.now();
  let lastEventT = 0;
  let lastEventPerf = performance.now();
  let expectedTrialDuration = 5000;

  function showOnly(which) {
    for (const node of [fixation, cue, stimulus, message]) node.classList.add("hidden");
    if (which) which.classList.remove("hidden");
  }

  function applyVisual(event) {
    const p = event.payload || {};
    const phase = String(event.phase || "idle").toLowerCase();

    el("phase").textContent = phase;
    el("condition").textContent = event.condition ?? "—";
    el("stimulusName").textContent = event.stimulus ?? p.kind ?? "—";
    el("eventTime").textContent = `${Number(event.t_ms || 0).toFixed(1)} ms`;
    el("trialBadge").textContent = `trial ${event.trial ?? "—"}`;

    lastEventT = Number(event.t_ms || 0);
    lastEventPerf = performance.now();

    if (Number.isFinite(Number(p.trial_duration_ms))) {
      expectedTrialDuration = Number(p.trial_duration_ms);
    }

    if (phase === "fixation") {
      showOnly(fixation);
    } else if (phase === "cue") {
      showOnly(cue);
      if (p.direction === "left") cue.style.transform = "rotate(-90deg)";
      else if (p.direction === "up") cue.style.transform = "rotate(0deg)";
      else if (p.direction === "down") cue.style.transform = "rotate(180deg)";
      else cue.style.transform = "rotate(90deg)";
    } else if (["stimulus", "stimulus_a", "stimulus_b"].includes(phase)) {
      showOnly(stimulus);
      const size = Number(p.size_px || 150);
      stimulus.style.width = `${Math.max(20, Math.min(500, size))}px`;
      if (p.shape === "square") stimulus.style.borderRadius = "8px";
      else stimulus.style.borderRadius = "50%";
    } else if (phase === "blank") {
      showOnly(null);
    } else {
      showOnly(message);
      message.textContent = p.text || phase || "idle";
    }
  }

  async function bootstrap() {
    const cfg = await fetch("/api/config").then(r => r.json());
    el("viewerFrame").src = cfg.viewer_url;

    try {
      const current = await fetch(cfg.task_state, {cache:"no-store"}).then(r => r.json());
      if (current && current.phase) applyVisual(current);
    } catch (_) {}

    const source = new EventSource(cfg.task_stream);

    source.onopen = () => {
      el("streamDot").classList.add("on");
      el("streamStatus").textContent = "task stream connected";
    };

    source.onerror = () => {
      el("streamDot").classList.remove("on");
      el("streamStatus").textContent = "reconnecting";
    };

    source.onmessage = ev => {
      try {
        applyVisual(JSON.parse(ev.data));
      } catch (e) {
        console.warn("bad task event", e);
      }
    };
  }

  function animateClock() {
    const dt = performance.now() - lastEventPerf;
    const t = lastEventT + dt;
    el("clock").textContent = `t ≈ ${t.toFixed(0)} ms`;
    const pct = expectedTrialDuration > 0 ? (t % expectedTrialDuration) / expectedTrialDuration * 100 : 0;
    el("timelineFill").style.width = `${Math.max(0, Math.min(100, pct))}%`;
    requestAnimationFrame(animateClock);
  }

  bootstrap().catch(err => {
    el("streamStatus").textContent = `error: ${err}`;
    console.error(err);
  });
  requestAnimationFrame(animateClock);
})();

