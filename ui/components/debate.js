import { openDebateStream } from "../api.js";
import { renderMd } from "../utils/markdown.js";
import { AGENT_DISPLAY_NAMES, avatarHtml } from "../utils/agents.js";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function esc(str) {
  return String(str ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const feed = document.getElementById("debate-feed");

const AGENT_THINKING = {
  researcher: "La Portera está investigando…",
  analyst:    "El Chulapo está calculando…",
  writer:     "El Pregonero está redactando…",
  reviewer:   "La Revisora está revisando…",
  vision:     "Berto está analizando las imágenes…",
};

function createTypingIndicator(name = "", agent = "", label = "") {
  const displayLabel = label || (agent ? (AGENT_THINKING[agent] ?? `${name} está analizando…`) : "");
  const el = document.createElement("div");
  el.className = "debate-message";
  el.id = "typing-indicator";
  el.innerHTML = `
    ${avatarHtml(agent, name)}
    <div class="message-bubble">
      ${displayLabel ? `<div class="agent-thinking-label">${esc(displayLabel)}</div>` : ""}
      <div class="typing-indicator">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
      </div>
    </div>`;
  return el;
}

function appendMessage({ agent, name, role, message, simulated }) {
  document.getElementById("typing-indicator")?.remove();
  const displayName = AGENT_DISPLAY_NAMES[agent] ?? name;
  const el = document.createElement("div");
  el.className = "debate-message";
  el.innerHTML = `
    ${avatarHtml(agent, name)}
    <div class="message-bubble">
      <div class="message-meta">
        <span class="agent-name">${esc(displayName)}</span>
        <span class="agent-role">${esc(role)}</span>
        ${simulated ? `<span class="simulated-badge">ejemplo</span>` : ""}
      </div>
      <div class="message-text">${renderMd(message)}</div>
    </div>`;
  feed.appendChild(el);
  el.scrollIntoView({ behavior: prefersReducedMotion ? "instant" : "smooth", block: "end" });
  feed.appendChild(createTypingIndicator());
}

function showSimulatedWarning() {
  if (document.getElementById("simulated-warning")) return;
  const el = document.createElement("div");
  el.id = "simulated-warning";
  el.className = "simulated-warning";
  el.textContent = "⚠️ Servidor de análisis no disponible. Mostrando datos de ejemplo, no reales.";
  feed.insertBefore(el, feed.firstChild);
}

export function renderStoredDebate(messages, simulated) {
  feed.innerHTML = "";
  if (simulated) showSimulatedWarning();
  for (const msg of messages) {
    appendMessage({ ...msg, simulated: simulated || msg.simulated });
  }
  document.getElementById("typing-indicator")?.remove();
}

export function runDebate(jobId, { onFirstAgent } = {}) {
  feed.innerHTML = "";
  feed.appendChild(createTypingIndicator("", "", "Uniendo a los agentes…"));
  let firstAgentFired = false;
  return new Promise((resolve, reject) => {
    openDebateStream(
      jobId,
      (data) => {
        if (data.simulated) showSimulatedWarning();
        if (!data.thinking && !data.message) return;
        if (!firstAgentFired) {
          firstAgentFired = true;
          onFirstAgent?.();
        }
        if (data.thinking) {
          document.getElementById("typing-indicator")?.remove();
          feed.appendChild(createTypingIndicator(data.name, data.agent));
        } else {
          appendMessage(data);
        }
      },
      () => {
        document.getElementById("typing-indicator")?.remove();
        resolve();
      },
      reject,
    );
  });
}
