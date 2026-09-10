"""HTML wrapper that lets a browser render mermaid source without a Streamlit build step."""

import pytest

from app.components.mermaid import mermaid_html

pytestmark = pytest.mark.unit


def test_embeds_the_source_verbatim_inside_a_mermaid_block() -> None:
    html = mermaid_html("graph TD;\n  A-->B;")
    assert '<pre class="mermaid">' in html
    assert "graph TD;" in html
    assert "A-->B;" in html


def test_loads_and_initializes_the_mermaid_library() -> None:
    html = mermaid_html("graph TD;\n  A-->B;")
    assert "mermaid" in html.lower()
    assert "initialize" in html


def test_uses_the_classic_script_tag_not_an_es_module() -> None:
    # An ES-module CDN import (type="module") was tried first and silently failed inside
    # Streamlit's sandboxed components iframe on the deployed app: the mermaid source showed
    # up as raw unstyled text, never diagrammed. The classic UMD <script src="..."> tag is
    # the pattern mermaid's own docs use for exactly this embed-in-arbitrary-HTML case.
    html = mermaid_html("graph TD;\n  A-->B;")
    assert '<script src="' in html
    assert 'type="module"' not in html


def test_does_not_html_escape_the_source() -> None:
    # our own generated sources embed HTML in node labels (e.g. "<p>__start__</p>"),
    # which mermaid needs verbatim to render the label, not as "&lt;p&gt;".
    html = mermaid_html("graph TD;\n  s([<p>__start__</p>])")
    assert "<p>__start__</p>" in html
