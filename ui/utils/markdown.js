import { marked }    from "https://esm.sh/marked@13";
import DOMPurify     from "https://esm.sh/dompurify@3";

marked.use({ breaks: true, gfm: true });

export function renderMd(text) {
  if (!text) return "";
  return DOMPurify.sanitize(marked.parse(String(text)));
}
