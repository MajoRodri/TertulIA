import { runDebate }   from "./components/debate.js";
import { showVerdict }  from "./components/verdict.js";
import { initApproval } from "./components/approval.js";
import { initChat, runChatVision } from "./components/chat.js";
import { startAnalysis, uploadImages } from "./api.js";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ── Hero bubbles: scroll convergence + 1s cycling, pause on hover ──
(function initHeroBubbles() {
  const hero    = document.getElementById("hero");
  const bubbles = [...document.querySelectorAll(".hero-bubble")];
  if (!hero || !bubbles.length) return;

  // Direction and scroll window per bubble (same logic as before)
  const POSITIONS = [
    { x:  0.36, y:  0.26, start: 0.00, end: 0.55 },  // tl
    { x: -0.36, y:  0.26, start: 0.08, end: 0.63 },  // tr
    { x:  0.36, y: -0.26, start: 0.16, end: 0.71 },  // bl
    { x: -0.36, y: -0.26, start: 0.24, end: 0.79 },  // br
    { x: -0.36, y:  0.00, start: 0.12, end: 0.67 },  // mr
  ];

  let activeIdx = 0;
  let timer     = null;

  function updateScroll() {
    const { top, height } = hero.getBoundingClientRect();
    const global = Math.max(0, Math.min(1, -top / (height * 0.65)));
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    bubbles.forEach((bubble, i) => {
      const { x, y, start, end } = POSITIONS[i];
      const local   = Math.max(0, Math.min(1, (global - start) / (end - start)));
      const scrollOpacity = Math.max(0, 1 - Math.max(0, (local - 0.75) / 0.25));
      const isActive = i === activeIdx;

      bubble.style.transform = `translate(${x * vw * local}px, ${y * vh * local}px) scale(${isActive ? 1.04 : 0.96})`;
      bubble.style.opacity   = String(scrollOpacity * (isActive ? 1.0 : 0.45));
    });
  }

  function activate(i) {
    bubbles.forEach((b, j) => b.classList.toggle("active", j === i));
    activeIdx = i;
    updateScroll();
  }

  function advance() { activate((activeIdx + 1) % bubbles.length); }
  function start()   { timer = setInterval(advance, 2000); }
  function stop()    { clearInterval(timer); }

  bubbles.forEach((bubble, i) => {
    bubble.addEventListener("mouseenter", () => { stop(); activate(i); });
    bubble.addEventListener("mouseleave", start);
  });

  function enable() {
    bubbles.forEach(b => { b.style.animation = "none"; });
    window.addEventListener("scroll", updateScroll, { passive: true });
    activate(0);
    if (!prefersReducedMotion) start();
  }

  const fallback = setTimeout(enable, 1800);
  bubbles[bubbles.length - 1].addEventListener("animationend", () => {
    clearTimeout(fallback);
    enable();
  }, { once: true });
})();

// ── Scroll reveal ─────────────────────────────────────────────
(function initScrollReveal() {
  const TARGETS = [
    ".how-section .eyebrow",
    ".how-section h2",
    ".how-section .section-sub",
    ".how-step",
    ".study-section .eyebrow",
    ".study-section h2",
    ".study-section .section-sub",
    ".study-block",
    ".study-pillar",
  ];

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      entry.target.classList.toggle("visible", entry.isIntersecting);
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });

  TARGETS.flatMap(sel => [...document.querySelectorAll(sel)]).forEach(el => {
    el.classList.add("reveal");
    // stagger siblings inside grids
    if (el.matches(".how-step, .study-pillar, .study-block")) {
      const idx = [...el.parentElement.children].indexOf(el);
      el.style.transitionDelay = `${idx * 0.1}s`;
    }
    observer.observe(el);
  });
})();

// ── Loading overlay ───────────────────────────────────────────
function showLoading() {
  const el = document.getElementById("loading-overlay");
  el.classList.remove("hidden", "fading");
  if (prefersReducedMotion) {
    const video = el.querySelector("video");
    video?.pause();
  }
}

function hideLoading() {
  const el = document.getElementById("loading-overlay");
  el.classList.add("fading");
  el.addEventListener("transitionend", () => el.classList.add("hidden"), { once: true });
}

// ── Navigation helpers ────────────────────────────────────────
const STEP_PANEL = {
  1: "panel-encargo",
  2: "panel-debate",
  3: "panel-chat",
  4: "panel-verdict",
  5: "panel-approval",
};
const ALL_PANEL_IDS = Object.values(STEP_PANEL);

function showPanel(id) {
  ALL_PANEL_IDS.forEach(p => document.getElementById(p)?.classList.add("hidden"));
  document.getElementById(id)?.classList.remove("hidden");
}

function setStep(n, state) {
  const el = document.getElementById(`step-${n}`);
  el.classList.remove("active", "done");
  el.classList.add(state);
}

function setLine(n, done) {
  if (done) document.getElementById(`line-${n}`).classList.add("done");
}

// Clicking a done/active step goes back to its panel
function initStepNav() {
  Object.entries(STEP_PANEL).forEach(([n, panelId]) => {
    document.getElementById(`step-${n}`)?.addEventListener("click", () => {
      const el = document.getElementById(`step-${n}`);
      if (el.classList.contains("done") || el.classList.contains("active")) {
        showPanel(panelId);
      }
    });
  });
}

// ── Show launcher once hero scrolls out of view ───────────────
(function initLauncherReveal() {
  const btn  = document.getElementById("launcher-btn");
  const hero = document.getElementById("hero");
  if (!btn || !hero) return;

  const observer = new IntersectionObserver(
    ([entry]) => { btn.classList.toggle("hidden", entry.isIntersecting); },
    { threshold: 0.1 }
  );
  observer.observe(hero);
})();

// ── Launcher widget ───────────────────────────────────────────
const launcherPanel = document.getElementById("launcher-panel");
const launcherBtn   = document.getElementById("launcher-btn");

const FOCUSABLE = 'a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])';

function openLauncher() {
  launcherPanel.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.documentElement.style.overflow = "hidden";
  const first = launcherPanel.querySelector(FOCUSABLE);
  first?.focus();
}
function closeLauncher() {
  launcherPanel.classList.add("hidden");
  document.body.style.overflow = "";
  document.documentElement.style.overflow = "";
  launcherBtn.focus();
}

launcherBtn.addEventListener("click", () =>
  launcherPanel.classList.contains("hidden") ? openLauncher() : closeLauncher()
);
document.getElementById("launcher-close").addEventListener("click", closeLauncher);
launcherPanel.addEventListener("click", (e) => {
  if (e.target === launcherPanel) closeLauncher();
});

document.addEventListener("keydown", (e) => {
  if (launcherPanel.classList.contains("hidden")) return;
  if (e.key === "Escape") { closeLauncher(); return; }
  if (e.key === "Tab") {
    const focusable = [...launcherPanel.querySelectorAll(FOCUSABLE)];
    if (!focusable.length) return;
    const first = focusable[0];
    const last  = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  }
});

document.getElementById("hero-scroll")?.addEventListener("click", openLauncher);

// ── Abandon analysis ──────────────────────────────────────────
document.getElementById("btn-exit").addEventListener("click", () => {
  location.reload();
});

// ── File validation & image picker ───────────────────────────
const MAX_FILE_MB    = 10;
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;
const ALLOWED_HINT   = "JPG o PNG · máx. 10 MB por archivo";

function validateImageFiles(files) {
  for (const f of files) {
    if (f.size > MAX_FILE_BYTES)
      return `"${f.name}" supera los ${MAX_FILE_MB} MB permitidos.`;
  }
  return null;
}

// Returns a getter () => File[] with thumbnail preview + per-file remove.
function attachImagePicker(inputId, hintId, previewId) {
  const input   = document.getElementById(inputId);
  const hint    = document.getElementById(hintId);
  const preview = document.getElementById(previewId);
  const managed = [];   // File[]

  function updateHint() {
    if (!hint) return;
    hint.style.color = "";
    hint.textContent = managed.length > 0
      ? `${managed.length} ${managed.length === 1 ? "archivo seleccionado" : "archivos seleccionados"}`
      : ALLOWED_HINT;
  }

  function render() {
    if (!preview) return;
    preview.innerHTML = "";
    managed.forEach((file, i) => {
      const url  = URL.createObjectURL(file);
      const wrap = document.createElement("div");
      wrap.className = "image-thumb-wrap";
      wrap.innerHTML = `
        <img class="image-thumb" src="${url}" alt="${file.name}" />
        <button type="button" class="image-thumb-remove" aria-label="Eliminar ${file.name}">×</button>`;
      wrap.querySelector(".image-thumb-remove").addEventListener("click", () => {
        URL.revokeObjectURL(url);
        managed.splice(i, 1);
        render();
        updateHint();
      });
      preview.appendChild(wrap);
    });
  }

  input?.addEventListener("change", (e) => {
    const incoming = Array.from(e.target.files ?? []);
    const err = validateImageFiles(incoming);
    if (err) {
      if (hint) { hint.textContent = err; hint.style.color = "var(--rojo)"; }
      e.target.value = "";
      return;
    }
    for (const f of incoming) {
      if (!managed.some(x => x.name === f.name && x.size === f.size)) managed.push(f);
    }
    e.target.value = "";  // reset so same file can be re-picked
    render();
    updateHint();
  });

  return () => managed;
}

const getFormImages = attachImagePicker("images",      "images-hint",      "images-preview");
const getChatImages = attachImagePicker("chat-images", "chat-images-hint", "chat-images-preview");

// ── Brief summary (panel 1 read-only view) ────────────────────
const RADIUS_LABELS = { 400: "400 m · 5 min andando", 800: "800 m · 10 min andando (recomendado)", 1200: "1.200 m · 15 min andando", 2000: "2.000 m · 25 min andando" };

function populateBriefSummary(brief, files) {
  const dl = document.getElementById("brief-summary");
  if (!dl) return;
  const rows = [
    ["Sector",       brief.business_type],
    ["Barrio",       brief.neighbourhood],
    brief.budget_eur ? ["Presupuesto", `${brief.budget_eur.toLocaleString("es-ES")} €`] : null,
    brief.area_m2    ? ["Superficie",  `${brief.area_m2} m²`] : null,
    ["Radio",        RADIUS_LABELS[brief.radius_m] ?? `${brief.radius_m} m`],
    brief.notes      ? ["Contexto",    brief.notes] : null,
  ].filter(Boolean);

  dl.innerHTML = rows.map(([label, value]) => `
    <div class="brief-row">
      <dt class="brief-label">${label}</dt>
      <dd class="brief-value">${value}</dd>
    </div>`).join("");

  if (files.length) {
    const thumbs = files.map(f => {
      const url = URL.createObjectURL(f);
      return `<img class="image-thumb" src="${url}" alt="${f.name}" style="width:64px;height:64px;object-fit:cover;border-radius:6px;border:1px solid var(--border)">`;
    }).join("");
    dl.innerHTML += `<div class="brief-row"><dt class="brief-label">Fotos</dt><dd class="brief-value"><div class="upload-preview" style="margin:0">${thumbs}</div></dd></div>`;
  }
}

// ── Brief form submit ─────────────────────────────────────────
document.getElementById("form-brief").addEventListener("submit", async (e) => {
  e.preventDefault();

  const btn = document.getElementById("btn-analyze");
  btn.disabled = true;
  btn.textContent = "Analizando…";

  const brief = {
    business_type: document.getElementById("sector").value,
    neighbourhood: document.getElementById("neighborhood").value,
    budget_eur:    parseFloat(document.getElementById("budget")?.value) || null,
    area_m2:       parseFloat(document.getElementById("area")?.value)   || null,
    radius_m:      parseInt(document.getElementById("radius")?.value)   || 800,
    notes:         document.getElementById("context")?.value?.trim() ?? "",
    user_profile:  document.getElementById("profile-select")?.value ?? "analyst",
  };

  try {
    const { job_id: jobId } = await startAnalysis(brief);

    const formFiles = getFormImages();
    if (formFiles.length) await uploadImages(jobId, formFiles);

    closeLauncher();
    document.querySelector(".main").classList.add("active");
    document.getElementById("main-backdrop").classList.add("active");
    document.getElementById("launcher-btn").classList.add("hidden");
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    document.getElementById("btn-exit").classList.remove("hidden");
    showLoading();

    populateBriefSummary(brief, getFormImages());

    document.getElementById("stepper").classList.remove("hidden");
    initStepNav();
    setStep(1, "done"); setLine(1, true);
    setStep(2, "active");
    showPanel("panel-debate");

    // Hide overlay as soon as the first event lands in the debate feed
    const feed = document.getElementById("debate-feed");
    const observer = new MutationObserver(() => { hideLoading(); observer.disconnect(); });
    observer.observe(feed, { childList: true });

    await runDebate(jobId);

    // Show continue button — user reads the debate then clicks to advance
    document.getElementById("debate-eyebrow").textContent = "Paso 2 · Completado";
    const debateActions = document.getElementById("debate-actions");
    debateActions.classList.remove("hidden");
    await new Promise((resolve) =>
      document.getElementById("btn-debate-continue").addEventListener("click", resolve, { once: true })
    );
    debateActions.classList.add("hidden");

    setStep(2, "done"); setLine(2, true);
    setStep(3, "active");
    showPanel("panel-chat");

    await initChat(jobId);   // resolves when user clicks "Continuar al veredicto"

    const chatFiles = getChatImages();
    if (chatFiles.length) {
      await uploadImages(jobId, chatFiles);
      await runChatVision(jobId);
    }

    setStep(3, "done"); setLine(3, true);
    setStep(4, "active");
    showPanel("panel-verdict");

    await showVerdict(jobId);

    setStep(4, "done"); setLine(4, true);
    setStep(5, "active");
    showPanel("panel-approval");

    initApproval(jobId);

  } catch (err) {
    console.error(err);
    btn.disabled = false;
    btn.textContent = "Analizar →";
    alert("Error al conectar con el servidor. Comprueba que FastAPI está en marcha.");
  }
});
