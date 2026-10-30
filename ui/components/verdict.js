import { fetchVerdict } from "../api.js";
import { avatarHtml } from "../utils/agents.js";
import { renderMd, renderMdInline } from "../utils/markdown.js";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const LIGHT_COLOR = { green: "var(--verde)", amber: "var(--amarillo)", red: "var(--rojo)" };
const LIGHT_TO_DOT = { green: "green", amber: "yellow", red: "red" };
const LIGHT_EMOJI  = { green: "🟢", amber: "🟡", red: "🔴" };
const LIGHT_LABEL  = { green: "Alta viabilidad", amber: "Viabilidad media", red: "Baja viabilidad" };

function _esc(str) {
  return String(str ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function _feed() {
  return document.getElementById("verdict-feed");
}

function _showTyping() {
  const feed = _feed();
  const el = document.createElement("div");
  el.id = "verdict-typing";
  el.className = "debate-message";
  el.innerHTML = `
    ${avatarHtml("berta", "Berta")}
    <div class="message-bubble">
      <div class="agent-thinking-label">Berta está preparando el veredicto…</div>
      <div class="typing-indicator">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
      </div>
    </div>`;
  feed.appendChild(el);
  el.scrollIntoView({ behavior: prefersReducedMotion ? "instant" : "smooth", block: "end" });
}

function _removeTyping() {
  document.getElementById("verdict-typing")?.remove();
}

function _buildMessage(data) {
  const light        = data.final_light ?? data.light ?? "amber";
  const rawConf      = data.final_confidence ?? data.confidence ?? 0;
  const confidence   = Number.isFinite(rawConf) ? Math.round(rawConf * 100) : 0;
  const confReliable = data.confidence_reliable !== false; // H-60: false when API has no real findings
  const summary      = data.summary ?? data.label ?? "";
  const reasons      = data.reasons ?? [];
  const color        = LIGHT_COLOR[light] ?? "var(--azul)";
  const dotClass     = LIGHT_TO_DOT[light] ?? "yellow";

  const reasonsHtml = reasons.length
    ? `<ul class="verdict-reasons-list">${reasons.map(r => `<li>${renderMdInline(r)}</li>`).join("")}</ul>`
    : "";

  const missingHtml = data.missing_data?.length
    ? `<div class="verdict-missing-wrap"><strong>Datos no disponibles</strong><ul>${data.missing_data.map(m => `<li>${renderMdInline(m)}</li>`).join("")}</ul></div>`
    : "";

  const warningsHtml = data.warnings?.length
    ? `<div class="verdict-warnings-wrap"><strong>Avisos de fuentes</strong><ul>${data.warnings.map(w => `<li>${renderMdInline(w)}</li>`).join("")}</ul></div>`
    : "";

  const confidenceHtml = confReliable
    ? `<div class="verdict-confidence">Confianza: ${confidence}%</div>
       <div class="confidence-bar">
         <div class="confidence-fill" style="width:${confidence}%;background:${color}"></div>
       </div>`
    : `<div class="verdict-confidence verdict-confidence--unreliable">Confianza: no calculada (sin datos verificados)</div>`;

  // D2: required by Foursquare ToS when their data contributed to the analysis
  const foursquareBadge = data.foursquare_used
    ? `<div class="foursquare-badge">
         <span class="foursquare-badge-text">Datos verificados con</span>
         <strong class="foursquare-badge-name">Foursquare</strong>
       </div>`
    : "";

  return `
    <div class="verdict-chat-card">
      <div class="verdict-chat-semaforo">
        <div class="traffic-lights" aria-label="Semáforo de viabilidad">
          <div class="traffic-dot green  ${dotClass === "green"  ? "active" : ""}" title="Alta viabilidad"></div>
          <div class="traffic-dot yellow ${dotClass === "yellow" ? "active" : ""}" title="Viabilidad media"></div>
          <div class="traffic-dot red    ${dotClass === "red"    ? "active" : ""}" title="Baja viabilidad"></div>
        </div>
        <div class="verdict-chat-info">
          <div class="verdict-label">${_esc(summary)}</div>
          ${confidenceHtml}
        </div>
      </div>
      ${reasonsHtml}
      ${missingHtml}
      ${warningsHtml}
      ${foursquareBadge}
    </div>`;
}

export async function showVerdict(jobId) {
  const feed = _feed();
  feed.innerHTML = "";

  _showTyping();

  let data;
  try {
    data = await fetchVerdict(jobId);
  } catch (err) {
    _removeTyping();
    const el = document.createElement("div");
    el.className = "debate-message";
    el.innerHTML = `
      ${avatarHtml("berta", "Berta")}
      <div class="message-bubble">
        <div class="message-meta"><span class="agent-name">Berta</span></div>
        <div class="message-text">No se pudo cargar el veredicto. Comprueba la conexión.</div>
      </div>`;
    feed.appendChild(el);
    throw err;
  }

  _removeTyping();

  if (data.simulated) {
    const warn = document.getElementById("verdict-simulated-warning");
    if (warn) warn.classList.remove("hidden");
  }

  const el = document.createElement("div");
  el.className = "debate-message";
  el.innerHTML = `
    ${avatarHtml("berta", "Berta")}
    <div class="message-bubble">
      <div class="message-meta">
        <span class="agent-name">Berta</span>
        <span class="agent-role">Coordinadora del análisis</span>
        ${data.simulated ? `<span class="simulated-badge">ejemplo</span>` : ""}
      </div>
      <div class="message-text">${_buildMessage(data)}</div>
    </div>`;
  feed.appendChild(el);
  el.scrollIntoView({ behavior: prefersReducedMotion ? "instant" : "smooth", block: "end" });

  document.getElementById("btn-verdict-continue").classList.remove("hidden");

  await new Promise((resolve) =>
    document.getElementById("btn-verdict-continue").addEventListener("click", resolve, { once: true })
  );
}
