import { fetchVerdict } from "../api.js";

const LIGHT_COLORS = { green: "var(--verde)", amber: "var(--amarillo)", red: "var(--rojo)" };
// amber maps to dot-yellow in HTML (dot IDs are green/yellow/red)
const LIGHT_TO_DOT = { green: "green", amber: "yellow", red: "red" };

export async function showVerdict(jobId) {
  const data = await fetchVerdict(jobId);

  // Support both real schema (final_light / final_confidence) and mock fallback
  const light      = data.final_light ?? data.signal ?? "amber";
  const confidence = data.final_confidence != null
    ? Math.round(data.final_confidence * 100)
    : (data.confidence ?? 0);

  ["green", "yellow", "red"].forEach((s) =>
    document.getElementById(`dot-${s}`)?.classList.remove("active")
  );
  document.getElementById(`dot-${LIGHT_TO_DOT[light] ?? light}`)?.classList.add("active");

  document.getElementById("verdict-label").textContent      = data.summary ?? data.label ?? "";
  document.getElementById("verdict-confidence").textContent = `Confianza: ${confidence}%`;

  const fill = document.getElementById("confidence-fill");
  fill.style.width      = `${confidence}%`;
  fill.style.background = LIGHT_COLORS[light] ?? "var(--azul)";

  document.getElementById("reasons-list").innerHTML = data.reasons
    .map((r) => `<div class="reason-item">${r}</div>`)
    .join("");
}
