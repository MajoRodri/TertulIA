import { runDebate }   from "./components/debate.js";
import { showVerdict }  from "./components/semaforo.js";
import { initApproval } from "./components/aprobacion.js";
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

// ── Hero buttons ─────────────────────────────────────────────
document.getElementById("btn-hero-start")?.addEventListener("click", () => scrollTo("panel-brief"));
document.getElementById("btn-hero-how")?.addEventListener("click",   () => scrollTo("how-section"));
document.getElementById("hero-scroll")?.addEventListener("click",    () => scrollTo("panel-brief"));

// ── Profile selector ─────────────────────────────────────────
document.getElementById("profile-select").addEventListener("change", (e) => {
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
    notes,
    user_profile:  document.getElementById("profile-select").value,
  };

  try {
    const { job_id: jobId } = await startAnalysis(brief);

    setStep(1, "done"); setLine(1, true);
    setStep(2, "active");
    showPanel("panel-debate");

    await runDebate(jobId);

    setStep(2, "done"); setLine(2, true);
    setStep(3, "active");
    showPanel("panel-verdict");

    await showVerdict(jobId);

    setStep(3, "done"); setLine(3, true);
    setStep(4, "active");
    showPanel("panel-approval");

    initApproval(jobId);

  } catch (err) {
    console.error(err);
    btn.disabled = false;
    btn.textContent = "Analizar →";
    alert("Error al conectar con el servidor. Comprueba que FastAPI está en marcha.");
  }
});
