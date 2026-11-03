"""Turn the HTML of a web page into plain text the agent can read.

The fetch server can do this itself, but its converter (readabilipy) breaks
when the server runs inside MCP on Windows. So we ask fetch for the raw HTML
and convert it here, with Python's standard library only: no new dependency,
and the same result on Windows, Mac and Linux.
"""

import re
from html.parser import HTMLParser

# Their content is code or drawings, never text for a person to read.
_SKIPPED_TAGS = {"script", "style", "noscript", "svg", "template"}
# Tags that start a new line on screen (paragraphs, titles, list items...).
_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
    "main", "nav", "ol", "p", "pre", "section", "table", "td", "th", "title",
    "tr", "ul",
}  # fmt: skip


class _TextExtractor(HTMLParser):
    """Reads the HTML piece by piece and keeps only the visible text."""

    def __init__(self) -> None:
        # convert_charrefs: "&amp;" becomes "&", "&euro;" becomes "€"...
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0  # > 0 while we are inside <script>, <style>...

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
            if tag == "li":
                self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            # Like a browser: a line break inside the HTML text is just a space.
            self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(html: str) -> str:
    """Visible text of a page: one block per line, at most one blank line in a row."""
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    # Clean each line: no spaces at the ends, never two spaces in a row.
    lines = (" ".join(line.split()) for line in "".join(extractor.parts).splitlines())
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()