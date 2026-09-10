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


def test_does_not_html_escape_the_source() -> None:
    # our own generated sources embed HTML in node labels (e.g. "<p>__start__</p>"),
    # which mermaid needs verbatim to render the label, not as "&lt;p&gt;".
    html = mermaid_html("graph TD;\n  s([<p>__start__</p>])")
    assert "<p>__start__</p>" in html
