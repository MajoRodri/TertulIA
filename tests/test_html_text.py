"""Tests for the HTML to text converter (src/tertulia/mcp/html_text.py)."""

from tertulia.mcp.html_text import html_to_text


def test_keeps_visible_text_one_block_per_line():
    html = (
        "<html><head><title>Café Sol</title></head>"
        "<body><h1>Carta</h1><p>Espresso 1,50 €</p></body></html>"
    )
    assert html_to_text(html) == "Café Sol\n\nCarta\n\nEspresso 1,50 €"


def test_drops_code_and_styles():
    html = (
        "<p>Hola</p><script>alert('x')</script>"
        "<style>p {color: red}</style><svg><text>logo</text></svg>"
    )
    assert html_to_text(html) == "Hola"


def test_lists_become_dashes():
    assert html_to_text("<ul><li>Wifi</li><li>Enchufes</li></ul>") == "- Wifi\n\n- Enchufes"


def test_html_entities_become_characters():
    assert html_to_text("<p>Caf&eacute; &amp; cowork &euro;</p>") == "Café & cowork €"


def test_extra_spaces_and_blank_lines_are_collapsed():
    html = "<div>  Abierto\n\n\n   de 8 a 20  </div><div></div><div></div><p>Atocha</p>"
    assert html_to_text(html) == "Abierto de 8 a 20\n\nAtocha"


def test_inline_tags_keep_the_spaces_between_words():
    html = "<p><b>Wifi</b> gratis y <a href='/'>terraza</a></p>"
    assert html_to_text(html) == "Wifi gratis y terraza"


def test_plain_text_passes_through():
    assert html_to_text("just text, no tags") == "just text, no tags"