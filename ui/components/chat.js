import { sendChatMessage, openVisionStream } from "../api.js";
import { renderMd } from "../utils/markdown.js";
import { AGENT_DISPLAY_NAMES, avatarHtml } from "../utils/agents.js";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function esc(str) {
  return String(str ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

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

export function initChat(jobId, imagePicker = null, docPicker = null) {
  const input       = document.getElementById("chat-input");
  const btnSend     = document.getElementById("btn-chat-send");
  const btnContinue = document.getElementById("btn-chat-continue");
  const fileInput   = document.getElementById("chat-images");
  const docInput    = document.getElementById("chat-docs");

  const getFiles    = () => imagePicker ? imagePicker.files() : [];
  const clearFiles  = () => imagePicker?.clear();
  const getDocs     = () => docPicker ? docPicker.files() : [];
  const getDocTypes = () => docPicker ? docPicker.types() : [];
  const clearDocs   = () => docPicker?.clear();

  return new Promise((resolve) => {
    btnContinue.addEventListener("click", function handler() {
      if (input.value.trim() || getFiles().length || getDocs().length) {
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
      const text     = input.value.trim();
      const files    = getFiles();
      const docs     = getDocs();
      const docTypes = getDocTypes();
      if (!text && !files.length && !docs.length) return;
      input.value = "";
      clearFiles();
      clearDocs();
      appendUserMessage(text, files, docs);
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
        }, docs, docTypes);
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
      if (docInput)  docInput.disabled  = locked;
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

function appendUserMessage(text, files = [], docs = []) {
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
    img.onload  = () => URL.revokeObjectURL(url);
    img.onerror = () => URL.revokeObjectURL(url);
    bubble.appendChild(img);
  }
  for (const doc of docs) {
    const badge = document.createElement("div");
    badge.className = "doc-badge";
    badge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> ${esc(doc.name)}`;
    bubble.appendChild(badge);
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
        <span class="agent-name">${esc(displayName)}</span>
        <span class="agent-role">${esc(role)}</span>
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
