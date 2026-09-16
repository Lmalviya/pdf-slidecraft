"""Unit tests for HTMLParserService."""

from app.models.enums import ElementType
from app.services.html_parser_service import HTMLParserService


def test_html_parser_with_bboxes():
    parser = HTMLParserService()
    html = """
    <html><body>
    <h1 data-bbox="[30, 20, 480, 60]">Main Header</h1>
    <p data-bbox="[30, 70, 480, 110]">This is paragraph text.</p>
    <ul>
      <li data-bbox="[30, 120, 480, 150]">Bullet 1</li>
      <li data-bbox="[30, 155, 480, 185]">Bullet 2</li>
    </ul>
    <img data-bbox="[30, 200, 250, 380]" alt="Diagram" />
    </body></html>
    """
    elements = parser.parse(html, 512, 660)
    assert len(elements) == 5
    assert elements[0].element_type == ElementType.HEADING
    assert elements[0].text == "Main Header"
    assert elements[1].element_type == ElementType.PARAGRAPH
    assert elements[4].element_type == ElementType.IMAGE


def test_html_parser_without_bboxes_flow_layout():
    parser = HTMLParserService()
    # Simulating what Qwen2.5-VL previously produced
    html = """
    ```html
    <html><body>
    <p>Achievements &amp; Positions</p>
    <ul>
      <li>Co-authored patent application on "AI risk evaluation".</li>
      <li>Received Narayana Murthy Award for excellence.</li>
    </ul>
    </body></html>
    ```
    """
    elements = parser.parse(html, 512, 660)
    assert len(elements) == 3
    assert elements[0].text == "Achievements & Positions"
    assert elements[1].element_type == ElementType.BULLET
    assert "Co-authored" in elements[1].text
    # Flow bboxes should be assigned
    assert elements[0].bbox.y1 < elements[1].bbox.y1
    assert elements[1].bbox.y1 < elements[2].bbox.y1
    assert elements[0].bbox.width > 0
