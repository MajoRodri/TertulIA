import { fetchVerdict } from "../api.js";

const LIGHT_COLORS = { green: "var(--verde)", amber: "var(--amarillo)", red: "var(--rojo)" };
// amber maps to dot-yellow in HTML (dot IDs are green/yellow/red)
const LIGHT_TO_DOT = { green: "green", amber: "yellow", red: "red" };

export async function showVerdict(jobId) {
  let data;
  try {
    data = await fetchVerdict(jobId);
  } catch (err) {
    const label = document.getElementById("verdict-label");
    if (label) label.textContent = "No se pudo cargar el veredicto — comprueba la conexión.";
    throw err;
  }

  if (data.simulated) {
    const warn = document.getElementById("verdict-simulated-warning");
    if (warn) warn.classList.remove("hidden");
  }

  // Support both real schema (final_light / final_confidence) and mock fallback
  const light      = data.final_light ?? data.light ?? "amber";
  const confidence = data.final_confidence != null
    ? Math.round(data.final_confidence * 100)
    : (data.confidence ?? 0);

  ["green", "yellow", "red"].forEach((s) =>
    document.getElementById(`dot-${s}`)?.classList.remove("active")
  );
  document.getElementById(`dot-${LIGHT_TO_DOT[light] ?? light}`)?.classList.add("active");

  const labelEl = document.getElementById("verdict-label");
  if (labelEl) labelEl.textContent = data.summary ?? data.label ?? "";

  const confEl = document.getElementById("verdict-confidence");
  if (confEl) confEl.textContent = `Confianza: ${confidence}%`;

  const fill = document.getElementById("confidence-fill");
  if (fill) {
    fill.style.width      = `${confidence}%`;
    fill.style.background = LIGHT_COLORS[light] ?? "var(--azul)";
  }

  const reasons = data.reasons ?? [];
  const reasonsEl = document.getElementById("reasons-list");
  if (reasonsEl)
    reasonsEl.innerHTML = reasons.map((r) => `<div class="reason-item">${r}</div>`).join("");

  const tokensEl = document.getElementById("verdict-tokens");
  if (tokensEl && data.tokens_used) {
    tokensEl.textContent = `Tokens utilizados: ${data.tokens_used.toLocaleString("es-ES")}`;
    tokensEl.classList.remove("hidden");
  }

  const missingWrap = document.getElementById("verdict-missing-wrap");
  const missingList = document.getElementById("verdict-missing-list");
  if (missingWrap && missingList && data.missing_data?.length) {
    missingList.innerHTML = data.missing_data.map((m) => `<li>${m}</li>`).join("");
    missingWrap.classList.remove("hidden");
  }

  const warningsWrap = document.getElementById("verdict-warnings-wrap");
  const warningsList = document.getElementById("verdict-warnings-list");
  if (warningsWrap && warningsList && data.warnings?.length) {
    warningsList.innerHTML = data.warnings.map((w) => `<li>${w}</li>`).join("");
    warningsWrap.classList.remove("hidden");
  }

  // Wait for the user to read the verdict and click continue
  await new Promise((resolve) =>
    document.getElementById("btn-verdict-continue").addEventListener("click", resolve, { once: true })
  );
}
