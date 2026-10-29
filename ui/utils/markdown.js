import { marked }    from "https://esm.sh/marked@13";
import DOMPurify     from "https://esm.sh/dompurify@3";

marked.use({ breaks: true, gfm: true });

function applyMath(html) {
  const k = window.katex;
  if (!k) return html;
  // Block math $$...$$
  html = html.replace(/\$\$([^$]+)\$\$/gs, (_, tex) => {
    try { return k.renderToString(tex.trim(), { displayMode: true, throwOnError: false, output: "html" }); }
    catch { return `<span>$$${tex}$$</span>`; }
  });
  // Inline math $...$
  html = html.replace(/\$([^$\n]+)\$/g, (_, tex) => {
    try { return k.renderToString(tex.trim(), { throwOnError: false, output: "html" }); }
    catch { return `<span>$${tex}$</span>`; }
  });
  return html;
}

export function renderMd(text) {
  if (!text) return "";
  return DOMPurify.sanitize(applyMath(marked.parse(String(text))));
}
