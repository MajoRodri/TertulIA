export const AGENT_DISPLAY_NAMES = {
  researcher: "La Portera",
  analyst:    "El Chulapo",
  writer:     "El Pregonero",
  reviewer:   "La Revisora",
  vision:     "Berto",
};

const AGENT_ICONS = {
  researcher: "portera",
  analyst:    "chulapo",
  writer:     "pregonero",
  reviewer:   "revisora",
  vision:     "berto",
};

export function avatarHtml(agent, name) {
  const icon        = AGENT_ICONS[agent];
  const displayName = AGENT_DISPLAY_NAMES[agent] ?? name;
  if (icon) {
    return `<div class="agent-avatar ${agent}"><img src="/assets/${icon}.png" alt="${displayName}" /></div>`;
  }
  return `<div class="agent-avatar ${agent}">${displayName.slice(0, 2).toUpperCase()}</div>`;
}
