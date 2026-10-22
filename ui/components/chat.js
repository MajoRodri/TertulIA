import { sendChatMessage } from "../api.js";

export function initChat(jobId) {
  const feed     = document.getElementById("chat-feed");
  const input    = document.getElementById("chat-input");
  const btnSend  = document.getElementById("btn-chat-send");
  const btnContinue = document.getElementById("btn-chat-continue");

  return new Promise((resolve) => {
    btnContinue.addEventListener("click", resolve, { once: true });

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
        await sendChatMessage(jobId, text, (msg) => appendAgentMessage(msg));
      } finally {
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

function appendUserMessage(text) {
  const feed = document.getElementById("chat-feed");
  const el = document.createElement("div");
  el.className = "chat-message user";
  el.innerHTML = `<div class="chat-bubble">${text}</div>`;
  feed.appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
}

function appendAgentMessage({ agent, name, role, message }) {
  const feed = document.getElementById("chat-feed");
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
}
