import { marked } from "https://esm.sh/marked@13";

marked.use({ breaks: true, gfm: true });

export function renderMd(text) {
  if (!text) return "";
  return marked.parse(String(text));
}
