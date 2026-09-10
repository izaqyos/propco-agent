"""Render mermaid source in the browser without any Python-side mermaid dependency.

Streamlit's ``st.code(..., language="mermaid")`` only syntax-highlights the text; it never
draws the diagram. This wraps the source in the small HTML/JS snippet mermaid.js itself
documents, for use with ``st.components.v1.html``.
"""

from __future__ import annotations

_MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"


def mermaid_html(source: str) -> str:
    """HTML that renders ``source`` as a mermaid diagram when loaded in a browser.

    ``source`` is server-generated (``AssetManagerService.mermaid()``), never user input, so
    it is embedded verbatim rather than HTML-escaped — our own diagrams intentionally embed
    HTML in node labels (e.g. ``<p>__start__</p>``), which mermaid needs literally to render.

    Uses the classic UMD bundle via a plain ``<script src>``, not an ES-module import: the
    module form was tried first and silently failed inside Streamlit's sandboxed components
    iframe on the deployed app (the source showed up as raw text, never diagrammed).
    """
    return (
        f'<pre class="mermaid">\n{source}\n</pre>\n'
        f'<script src="{_MERMAID_JS}"></script>\n'
        f"<script>\n"
        f"  mermaid.initialize({{ startOnLoad: true }});\n"
        f"</script>"
    )
