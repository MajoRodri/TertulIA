import { runDebate }   from "./components/debate.js";
import { showVerdict }  from "./components/semaforo.js";
import { initApproval } from "./components/aprobacion.js";
import { initChat }     from "./components/chat.js";
import { startAnalysis } from "./api.js";

// ── Navigation helpers ────────────────────────────────────────
function showPanel(id) {
  document.getElementById(id).classList.remove("hidden");
  document.getElementById(id).scrollIntoView({ behavior: "smooth", block: "start" });
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

// ── Launcher widget ───────────────────────────────────────────
const launcherPanel = document.getElementById("launcher-panel");

function openLauncher()  { launcherPanel.classList.remove("hidden"); }
function closeLauncher() { launcherPanel.classList.add("hidden"); }

document.getElementById("launcher-btn").addEventListener("click", () =>
  launcherPanel.classList.toggle("hidden")
);
document.getElementById("launcher-close").addEventListener("click", closeLauncher);
launcherPanel.addEventListener("click", (e) => {
  if (e.target === launcherPanel) closeLauncher();
});

// ── Hero buttons open the launcher ───────────────────────────
document.getElementById("btn-hero-start")?.addEventListener("click", openLauncher);
document.getElementById("btn-hero-how")?.addEventListener("click",   () => scrollTo("how-section"));
document.getElementById("hero-scroll")?.addEventListener("click",    openLauncher);

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
    document.getElementById("stepper").classList.remove("hidden");

    setStep(1, "done"); setLine(1, true);
    setStep(2, "active");
    showPanel("panel-debate");

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
