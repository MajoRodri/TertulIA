import { sendChatMessage, openVisionStream } from "../api.js";
import { renderMd } from "../utils/markdown.js";
import { AGENT_DISPLAY_NAMES, avatarHtml } from "../utils/agents.js";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function initChat(jobId) {
  const feed     = document.getElementById("chat-feed");
  const input    = document.getElementById("chat-input");
  const btnSend  = document.getElementById("btn-chat-send");
  const btnContinue = document.getElementById("btn-chat-continue");

  return new Promise((resolve) => {
    btnContinue.addEventListener("click", function handler() {
      if (input.value.trim()) {
        const ok = window.confirm("Tienes un mensaje sin enviar. ¿Continuar al veredicto de todas formas?");
        if (!ok) return;
      }
      btnContinue.removeEventListener("click", handler);
      resolve();
    });

    btnSend.addEventListener("click", () => handleSend());
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
    });

    async function handleSend() {
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      appendUserMessage(text);
      setInputLocked(true);
      try {
        await sendChatMessage(jobId, text, (msg) => {
          if (msg.thinking) {
            showTypingIndicator(msg.name, msg.agent);
          } else {
            removeTypingIndicator();
            appendAgentMessage(msg);
          }
        });
      } finally {
        removeTypingIndicator();
        setInputLocked(false);
        input.focus();
      }
    }

    function setInputLocked(locked) {
      input.disabled   = locked;
      btnSend.disabled = locked;
      if (locked) btnSend.textContent = "Enviando…";
      else        btnSend.textContent = "Enviar";
    }
  });
}

export function runChatVision(jobId) {
  return new Promise((resolve) => {
    openVisionStream(
      jobId,
      (msg) => {
        if (msg.thinking) showTypingIndicator(msg.name, msg.agent);
        else { removeTypingIndicator(); appendAgentMessage(msg); }
      },
      () => { removeTypingIndicator(); resolve(); },
      () => { removeTypingIndicator(); resolve(); },
    );
  });
}

function showTypingIndicator(name = "", agent = "") {
  const feed = document.getElementById("chat-feed");
  removeTypingIndicator();
  const el = document.createElement("div");
  el.id = "chat-typing";
  el.className = "debate-message";
  el.innerHTML = `
    ${avatarHtml(agent, name)}
    <div class="message-bubble">
      <div class="typing-indicator">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
      </div>
    </div>`;
  feed.appendChild(el);
  el.scrollIntoView({ behavior: prefersReducedMotion ? "instant" : "smooth", block: "end" });
}

function removeTypingIndicator() {
  document.getElementById("chat-typing")?.remove();
}

function appendUserMessage(text) {
  const feed = document.getElementById("chat-feed");
  const el = document.createElement("div");
  el.className = "chat-message user";
  el.innerHTML = `<div class="chat-bubble">${text}</div>`;
  feed.appendChild(el);
  el.scrollIntoView({ behavior: prefersReducedMotion ? "instant" : "smooth", block: "end" });
}

function appendAgentMessage({ agent, name, role, message }) {
  const feed = document.getElementById("chat-feed");
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
}
