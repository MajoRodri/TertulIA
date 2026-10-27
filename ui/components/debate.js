import { openDebateStream } from "../api.js";
import { renderMd } from "../utils/markdown.js";
import { AGENT_DISPLAY_NAMES, avatarHtml } from "../utils/agents.js";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const feed = document.getElementById("debate-feed");

const AGENT_THINKING = {
  researcher: "La Portera está investigando…",
  analyst:    "El Chulapo está calculando…",
  writer:     "El Pregonero está redactando…",
  reviewer:   "La Revisora está revisando…",
  vision:     "Berto está analizando las imágenes…",
};

function createTypingIndicator(name = "", agent = "") {
  const label = agent
    ? (AGENT_THINKING[agent] ?? `${name} está analizando…`)
    : "";
  const el = document.createElement("div");
  el.className = "debate-message";
  el.id = "typing-indicator";
  el.innerHTML = `
    ${avatarHtml(agent, name)}
    <div class="message-bubble">
      ${label ? `<div class="agent-thinking-label">${label}</div>` : ""}
      <div class="typing-indicator">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
      </div>
    </div>`;
  return el;
}

function appendMessage({ agent, name, role, message }) {
  document.getElementById("typing-indicator")?.remove();
  const displayName = AGENT_DISPLAY_NAMES[agent] ?? name;
  const el = document.createElement("div");
  el.className = "debate-message";
  el.innerHTML = `
    ${avatarHtml(agent, name)}
    <div class="message-bubble">
      <div class="message-meta">
        <span class="agent-name">${displayName}</span>
        <span class="agent-role">${role}</span>
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
  el.textContent = "⚠️ Servidor de análisis no disponible — mostrando datos de ejemplo, no reales.";
  feed.insertBefore(el, feed.firstChild);
}

export function runDebate(jobId) {
  feed.innerHTML = "";
  feed.appendChild(createTypingIndicator());
  return new Promise((resolve, reject) => {
    openDebateStream(
      jobId,
      (data) => {
        if (data.simulated) { showSimulatedWarning(); return; }
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
