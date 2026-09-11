"""Render mermaid source in the browser without any Python-side mermaid dependency.

Streamlit's ``st.code(..., language="mermaid")`` only syntax-highlights the text; it never
draws the diagram. This wraps the source in a small HTML/JS snippet, for use with
``st.components.v1.html``.
"""

from __future__ import annotations

import json

_MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
_TARGET_ID = "propco-mermaid-graph"


def mermaid_html(source: str) -> str:
    """HTML that renders ``source`` as a mermaid diagram when loaded in a browser.

    ``source`` is server-generated (``AssetManagerService.mermaid()``), never user input;
    ``json.dumps`` embeds it as a JS string literal, which handles quoting/newlines without
    touching ``<``/``>`` — our own diagrams intentionally embed HTML in node labels (e.g.
    ``<p>__start__</p>``), which mermaid needs literally to render the label.

    Two things learned by testing this against a real browser rather than trusting the docs:
    a ``type="module"`` CDN import silently failed inside Streamlit's sandboxed components
    iframe (fixed by the classic UMD ``<script src>`` tag below), and ``startOnLoad``'s DOM
    auto-scan rendered every node at zero size on the deployed app (a real ``<svg>`` was
    created, but with ``viewBox="-8 -8 16 16"`` — invisible). ``mermaid.render()`` returns
    fully computed SVG directly, side-stepping that measurement race.
    """
    return (
        f'<div id="{_TARGET_ID}"></div>\n'
        f'<script src="{_MERMAID_JS}"></script>\n'
        f"<script>\n"
        f"  mermaid.initialize({{ startOnLoad: false }});\n"
        f"  mermaid.render('propco-mermaid-svg', {json.dumps(source)}).then(({{ svg }}) => {{\n"
        f"    document.getElementById('{_TARGET_ID}').innerHTML = svg;\n"
        f"  }});\n"
        f"</script>"
    )
