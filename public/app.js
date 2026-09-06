(() => {
  "use strict";

  const cards = [...document.querySelectorAll(".evidence-card")];
  const filterButtons = [...document.querySelectorAll("[data-filter]")];
  const filterNote = document.querySelector("#filter-note");
  const layer = document.querySelector("[data-inspect-layer]");
  const drawerTitle = document.querySelector("#inspect-title");
  const drawerContent = document.querySelector("[data-drawer-content]");
  const closeTargets = document.querySelectorAll("[data-close-inspect]");

  const details = {
    ao: {
      title: "AO execution plane",
      state: "mixed evidence",
      stateClass: "is-amber",
      intro: "AO is the execution and supervision boundary. The project records a healthy daemon and an authorized OpenCode surface, while refusing to infer a final spawn or completion claim from that alone.",
      rows: [
        ["health", "healthz=ok · readyz=ready"],
        ["authorized", "OpenCode only"],
        ["spawn", "blocked_unknown_payload"],
        ["lifecycle", "unverified for final run"],
        ["source", ".forge/ao-surface.json"]
      ],
      note: "Open edge: the raw session creation payload and response semantics still need an explicitly approved, observed worker launch."
    },
    runner: {
      title: "Bounded AO Runner contract",
      state: "implemented / not live-proven",
      stateClass: "is-amber",
      intro: "The runner uses documented AO CLI flags, polls the observed session, checks a worktree artifact, and applies one watchdog nudge before killing a no-op or hidden-blocked session.",
      rows: [
        ["schema", "forge.ao-runner.v1"],
        ["events", "spawn · poll · check · send · kill · verdict"],
        ["pass gate", "artifact + optional independent verifier"],
        ["cross-harness", "separate readiness gate · requires 2"],
        ["live status", "implementation tested with fakes; AO lifecycle open"]
      ],
      note: "The contract is implemented and unit-tested, but the real AO worker proof still requires an artifact-producing, independently verified run."
    },
    c0: {
      title: "C0 baseline and repair",
      state: "observed outcome",
      stateClass: "is-green",
      intro: "The frozen verifier separated the red baseline from the repaired candidate. This is outcome evidence for the bounded c0-name-normalizer-v1 task, not a claim about a broader domain.",
      rows: [
        ["baseline", "exit 1 · test_failure"],
        ["repair", "1 bounded attempt"],
        ["final", "exit 0 · 4 frozen tests passed"],
        ["readback", "status=passed · events=5"],
        ["source", "evals/results/submission-c0-82dffafc.json"]
      ],
      note: "The latest full project regression result is recorded separately as 61 passing tests."
    },
    skill: {
      title: "Candidate skill artifact",
      state: "candidate / not promoted",
      stateClass: "is-amber",
      intro: "A real GPT-5 Nano reflection call returned strict structured output after the C0 failure. Forge stores the result as a candidate and keeps the gate boundary explicit.",
      rows: [
        ["skill id", "c0-name-normalizer-v1"],
        ["model", "gpt-5-nano"],
        ["scope", "bounded C0 task family"],
        ["gate", "not run · status=candidate"],
        ["reflection", "reflection_error=null"]
      ],
      note: "No cross-domain or cross-harness transfer is implied until a separate validation and held-out result exists."
    },
    trace: {
      title: "Neatlogs trace readback",
      state: "observed readback",
      stateClass: "is-green",
      intro: "The submission workflow was finalized in Neatlogs and read back. The evidence includes the trace identifier, seven persisted spans, and required application input/output fields.",
      rows: [
        ["verify", "exit 0"],
        ["trace", "6f969ec0305657630aeb0b959cc189ab"],
        ["spans", "7 persisted spans"],
        ["fields", "input / output present"],
        ["fallback", "local JSONL remains authoritative"]
      ],
      note: "This is a readback claim for the recorded smoke workflow, not a claim that every Forge path is instrumented."
    },
    blockers: {
      title: "Open edges and blockers",
      state: "unverified",
      stateClass: "is-amber",
      intro: "A useful evidence surface makes the missing proof easy to find. These edges remain open in the source project.",
      rows: [
        ["AO", "spawn payload + final lifecycle"],
        ["transfer", "second harness result not observed"],
        ["Supermemory", "setup TODO · local registry active"],
        ["boundary", "no claim without an observed run"]
      ],
      note: "Next proof should be narrow: explicitly approve a tiny AO worker launch, record its artifact and lifecycle, then run a separate transfer gate."
    }
  };

  function updateFilter(filter) {
    let visible = 0;
    cards.forEach((card) => {
      const tags = (card.dataset.tags || "").split(/\s+/);
      const show = filter === "all" || tags.includes(filter);
      card.classList.toggle("is-hidden", !show);
      if (show) visible += 1;
    });

    filterButtons.forEach((button) => {
      const selected = button.dataset.filter === filter;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });

    if (filterNote) {
      filterNote.textContent = `${visible} evidence card${visible === 1 ? "" : "s"}`;
    }
  }

  function openDetail(key) {
    const detail = details[key];
    if (!detail || !layer || !drawerContent || !drawerTitle) return;

    drawerTitle.textContent = detail.title;
    drawerContent.innerHTML = `
      <div class="detail-status"><span class="status-dot ${detail.stateClass}" aria-hidden="true"></span>${detail.state}</div>
      <p>${detail.intro}</p>
      <dl class="detail-list">
        ${detail.rows.map(([label, value]) => `<div class="detail-row"><dt>${label}</dt><dd>${value}</dd></div>`).join("")}
      </dl>
      <p class="detail-note"><strong>Boundary:</strong> ${detail.note}</p>
    `;
    layer.hidden = false;
    document.body.classList.add("drawer-open");
    const closeButton = layer.querySelector(".close-button");
    if (closeButton) closeButton.focus();
  }

  function closeDetail() {
    if (!layer) return;
    layer.hidden = true;
    document.body.classList.remove("drawer-open");
  }

  filterButtons.forEach((button) => {
    button.addEventListener("click", () => updateFilter(button.dataset.filter));
  });

  document.querySelectorAll("[data-inspect]").forEach((button) => {
    button.addEventListener("click", () => openDetail(button.dataset.inspect));
  });

  closeTargets.forEach((target) => target.addEventListener("click", closeDetail));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && layer && !layer.hidden) closeDetail();
  });

  updateFilter("all");
})();
