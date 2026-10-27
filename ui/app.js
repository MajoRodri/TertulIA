import { runDebate }   from "./components/debate.js";
import { showVerdict }  from "./components/verdict.js";
import { initApproval } from "./components/approval.js";
import { initChat }     from "./components/chat.js";
import { startAnalysis } from "./api.js";

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
    start();
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
}

function hideLoading() {
  const el = document.getElementById("loading-overlay");
  el.classList.add("fading");
  el.addEventListener("transitionend", () => el.classList.add("hidden"), { once: true });
}

// ── Navigation helpers ────────────────────────────────────────
function showPanel(id) {
  document.getElementById(id).classList.remove("hidden");
}

function setStep(n, state) {
  const el = document.getElementById(`step-${n}`);
  el.classList.remove("active", "done");
  el.classList.add(state);
}

function setLine(n, done) {
  if (done) document.getElementById(`line-${n}`).classList.add("done");
}

function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
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

function openLauncher()  {
  launcherPanel.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}
function closeLauncher() {
  launcherPanel.classList.add("hidden");
  document.body.style.overflow = "";
}

document.getElementById("launcher-btn").addEventListener("click", () =>
  launcherPanel.classList.toggle("hidden")
);
document.getElementById("launcher-close").addEventListener("click", closeLauncher);
launcherPanel.addEventListener("click", (e) => {
  if (e.target === launcherPanel) closeLauncher();
});

document.getElementById("hero-scroll")?.addEventListener("click", openLauncher);

// ── Profile selector ─────────────────────────────────────────
document.getElementById("profile-select")?.addEventListener("change", (e) => {
  document.getElementById("notice-entrepreneur").classList.toggle("hidden", e.target.value !== "entrepreneur");
});

// ── Brief form submit ─────────────────────────────────────────
document.getElementById("form-brief").addEventListener("submit", async (e) => {
  e.preventDefault();

  const btn = document.getElementById("btn-analyze");
  btn.disabled = true;
  btn.textContent = "Analizando…";

  const areaRaw    = document.getElementById("area")?.value;
  const contextRaw = document.getElementById("context")?.value ?? "";
  const notes      = [contextRaw, areaRaw ? `Superficie: ${areaRaw} m²` : ""]
    .filter(Boolean).join(" | ");

  const brief = {
    business_type: document.getElementById("sector").value,
    neighbourhood: document.getElementById("neighborhood").value,
    budget_eur:    parseFloat(document.getElementById("budget")?.value) || null,
    radius_m:      parseInt(document.getElementById("radius")?.value) || 800,
    notes,
    user_profile:  document.getElementById("profile-select").value,
  };

  try {
    const { job_id: jobId } = await startAnalysis(brief);

    closeLauncher();
    document.querySelector(".main").classList.add("active");
    showLoading();

    document.getElementById("stepper").classList.remove("hidden");
    setStep(1, "done"); setLine(1, true);
    setStep(2, "active");
    showPanel("panel-debate");

    // Hide overlay as soon as the first event lands in the debate feed
    const feed = document.getElementById("debate-feed");
    const observer = new MutationObserver(() => { hideLoading(); observer.disconnect(); });
    observer.observe(feed, { childList: true });

    await runDebate(jobId);

    setStep(2, "done"); setLine(2, true);
    setStep(3, "active");
    showPanel("panel-chat");

    await initChat(jobId);   // resolves when user clicks "Continuar al veredicto"

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
