from __future__ import annotations

from cpw_variability.parser import parse_html_content


def test_parse_html_content_extracts_core_fields():
    html = """
    <html>
      <body>
        <h2>Alpha-Beta</h2>
        <p><strong>Alpha-Beta</strong> is a minimax search algorithm.</p>
        <a href="/Quiescence_Search">Quiescence Search</a>
        <div id="catlinks"><a href="/Category:Search">Search</a></div>
      </body>
    </html>
    """

    parsed = parse_html_content(html)
    assert "Alpha-Beta" in parsed["headings"]
    assert "Quiescence Search" in parsed["links"]
    assert "Alpha-Beta" in parsed["bold_terms"]
    assert "Search" in parsed["categories"]
    assert "minimax" in parsed["text"]
    assert parsed["sentences"]
