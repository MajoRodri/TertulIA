export const AGENT_DISPLAY_NAMES = {
  researcher: "La Portera",
  analyst:    "El Chulapo",
  writer:     "El Pregonero",
  reviewer:   "La Revisora",
  vision:     "Berto",
  berta:      "Berta",
};

const AGENT_ICONS = {
  researcher: "portera",
  analyst:    "chulapo",
  writer:     "pregonero",
  reviewer:   "revisora",
  vision:     "berto",
  berta:      "berta",
};

function _esc(str) {
  return String(str ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function avatarHtml(agent, name) {
  const icon        = AGENT_ICONS[agent];
  const displayName = AGENT_DISPLAY_NAMES[agent] ?? name;
  if (icon) {
    return `<div class="agent-avatar ${_esc(agent)}"><img src="/assets/${icon}.png" alt="${_esc(displayName)}" /></div>`;
  }
  return `<div class="agent-avatar ${_esc(agent)}">${_esc(String(displayName).slice(0, 2).toUpperCase())}</div>`;
}
