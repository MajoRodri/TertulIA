import { openDebateStream } from "../api.js";

const feed = document.getElementById("debate-feed");

function createTypingIndicator(name = "", agent = "") {
  const el = document.createElement("div");
  el.className = "debate-message";
  el.id = "typing-indicator";
  el.innerHTML = `
    <div class="agent-avatar ${agent}" style="${agent ? "" : "background:var(--border)"}">
      ${agent ? name.slice(0, 2).toUpperCase() : ""}
    </div>
    <div class="message-bubble">
      ${name ? `<div class="agent-thinking-label">${name} está analizando…</div>` : ""}
      <div class="typing-indicator">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
      </div>
    </div>`;
  return el;
}

function appendMessage({ agent, name, role, message }) {
  document.getElementById("typing-indicator")?.remove();
  const el = document.createElement("div");
  el.className = "debate-message";
  el.innerHTML = `
    <div class="agent-avatar ${agent}">${name.slice(0, 2).toUpperCase()}</div>
    <div class="message-bubble">
      <div class="message-meta">
        <span class="agent-name">${name}</span>
        <span class="agent-role">${role}</span>
      </div>
      <p class="message-text">${message}</p>
    </div>`;
  feed.appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
  feed.appendChild(createTypingIndicator());
}

export function runDebate(jobId) {
  feed.innerHTML = "";
  feed.appendChild(createTypingIndicator());
  return new Promise((resolve, reject) => {
    openDebateStream(
      jobId,
      (data) => {
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
