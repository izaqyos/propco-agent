"""HTML wrapper that lets a browser render mermaid source without a Streamlit build step."""

import json

import pytest

from app.components.mermaid import mermaid_html

pytestmark = pytest.mark.unit


def test_embeds_the_source_as_a_javascript_string() -> None:
    html = mermaid_html("graph TD;\n  A-->B;")
    assert json.dumps("graph TD;\n  A-->B;") in html


def test_calls_mermaid_render_explicitly_not_startonload_autoscan() -> None:
    # startOnLoad's DOM auto-scan measured every node/label as zero-size on the deployed app
    # (a real <svg> got created, but with viewBox="-8 -8 16 16" — a 16x16 px diagram, invisible
    # at normal scale). mermaid.render() returns computed SVG directly, side-stepping whatever
    # timing/measurement race caused that. Verified with an actual browser before this change.
    html = mermaid_html("graph TD;\n  A-->B;")
    assert "mermaid.render(" in html
    assert "startOnLoad: true" not in html


def test_uses_the_classic_script_tag_not_an_es_module() -> None:
    # An ES-module CDN import (type="module") was tried first and silently failed inside
    # Streamlit's sandboxed components iframe on the deployed app: the mermaid source showed
    # up as raw unstyled text, never diagrammed. The classic UMD <script src="..."> tag is
    # the pattern mermaid's own docs use for exactly this embed-in-arbitrary-HTML case.
    html = mermaid_html("graph TD;\n  A-->B;")
    assert '<script src="' in html
    assert 'type="module"' not in html


def test_does_not_break_on_html_embedded_in_node_labels() -> None:
    # our own generated sources embed HTML in node labels (e.g. "<p>__start__</p>"), which
    # mermaid needs verbatim to render the label. json.dumps preserves it as-is (it only
    # escapes quotes/newlines/backslashes, never "<"/">"), so the round-trip is exact.
    source = "graph TD;\n  s([<p>__start__</p>])"
    html = mermaid_html(source)
    assert json.dumps(source) in html
