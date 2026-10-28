import { sendChatMessage, openVisionStream } from "../api.js";
import { renderMd } from "../utils/markdown.js";
import { AGENT_DISPLAY_NAMES, avatarHtml } from "../utils/agents.js";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function renderChatHistory(chatHistory) {
  for (const entry of chatHistory) {
    if (entry.role === "user") {
      appendUserMessage(entry.text, []);
    } else {
      appendAgentMessage({
        agent: "analyst", name: "Analista",
        role: "Viabilidad financiera", message: entry.text,
      });
    }
  }
}

export function initChat(jobId, imagePicker = null) {
  const input       = document.getElementById("chat-input");
  const btnSend     = document.getElementById("btn-chat-send");
  const btnContinue = document.getElementById("btn-chat-continue");
  const fileInput   = document.getElementById("chat-images");

  const getFiles  = () => imagePicker ? imagePicker.files() : [];
  const clearFiles = () => imagePicker?.clear();

  return new Promise((resolve) => {
    btnContinue.addEventListener("click", function handler() {
      if (input.value.trim() || getFiles().length) {
        const ok = window.confirm("Tienes contenido sin enviar. ¿Continuar al veredicto de todas formas?");
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
      const text  = input.value.trim();
      const files = getFiles();
      if (!text && !files.length) return;
      input.value = "";
      clearFiles();
      appendUserMessage(text, files);
      setInputLocked(true);
      try {
        await sendChatMessage(jobId, text, files, (msg) => {
          if (msg.warning) {
            appendWarningMessage(msg.warning);
          } else if (msg.thinking) {
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
      if (fileInput) fileInput.disabled = locked;
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

function appendUserMessage(text, files = []) {
  const feed = document.getElementById("chat-feed");
  const el = document.createElement("div");
  el.className = "chat-message user";
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  for (const file of files) {
    const url = URL.createObjectURL(file);
    const img = Object.assign(document.createElement("img"), {
      src: url, className: "upload-thumb",
    });
    img.onload = () => URL.revokeObjectURL(url);
    bubble.appendChild(img);
  }
  if (text) {
    const span = document.createElement("span");
    span.textContent = text;
    bubble.appendChild(span);
  }
  el.appendChild(bubble);
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

function appendWarningMessage(text) {
  const feed = document.getElementById("chat-feed");
  const el = document.createElement("div");
  el.className = "chat-warning";
  const span = document.createElement("span");
  span.textContent = text;
  el.appendChild(span);
  feed.appendChild(el);
  el.scrollIntoView({ behavior: prefersReducedMotion ? "instant" : "smooth", block: "end" });
}
