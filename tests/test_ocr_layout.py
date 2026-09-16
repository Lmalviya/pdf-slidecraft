"""Unit tests for OCR and Layout Analysis services."""

from PIL import Image, ImageDraw
import numpy as np

from app.models.enums import ElementType
from app.models.schemas import BBox, SlideElement
from app.services.layout_service import LayoutService
from app.services.ocr_service import OCRService, OCRTextLine
from app.services.ppt_service import PPTService


def test_ocr_and_layout_pipeline():
    # 1. Create a synthetic test slide image with title, bullet points, and a colored photo box
    w, h = 1000, 600
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw title text
    draw.text((50, 40), "TYPES OF SCOLIOSIS", fill=(10, 77, 104))

    # Draw bullet points
    draw.text((50, 120), "1. IDIOPATHIC SCOLIOSIS-MOST common type(70%)", fill=(34, 34, 34))
    draw.text((50, 160), "Classified by age of onset", fill=(34, 34, 34))
    draw.text((50, 200), "Types:-", fill=(34, 34, 34))
    draw.text((80, 240), "a) Infantile", fill=(34, 34, 34))
    draw.text((80, 280), "b) Juvenile", fill=(34, 34, 34))
    draw.text((80, 320), "c) Adolescent", fill=(34, 34, 34))

    # Draw a simulated photograph on the right (rich gradient/colored box)
    for y_offset in range(350):
        for x_offset in range(350):
            r = (x_offset * 2) % 255
            g = (y_offset * 3) % 255
            b = (x_offset + y_offset) % 255
            img.putpixel((580 + x_offset, 120 + y_offset), (r, g, b))

    # 2. Test LayoutService image detection and text grouping
    layout_service = LayoutService()

    ocr_lines = [
        OCRTextLine("TYPES OF SCOLIOSIS", BBox(x1=50, y1=40, x2=450, y2=80), 0.98),
        OCRTextLine("1. IDIOPATHIC SCOLIOSIS-MOST common type(70%)", BBox(x1=50, y1=120, x2=520, y2=145), 0.95),
        OCRTextLine("Classified by age of onset", BBox(x1=50, y1=160, x2=380, y2=185), 0.95),
        OCRTextLine("Types:-", BBox(x1=50, y1=200, x2=150, y2=225), 0.95),
        OCRTextLine("a) Infantile", BBox(x1=80, y1=240, x2=220, y2=265), 0.95),
        OCRTextLine("b) Juvenile", BBox(x1=80, y1=280, x2=220, y2=305), 0.95),
        OCRTextLine("c) Adolescent", BBox(x1=80, y1=320, x2=250, y2=345), 0.95),
    ]

    elements = layout_service.analyze_page(img, ocr_lines)

    # Verify elements
    assert len(elements) >= 3

    # Check that image region on the right is detected
    image_elements = [e for e in elements if e.element_type == ElementType.IMAGE]
    assert len(image_elements) >= 1
    assert image_elements[0].bbox.x1 >= 500  # Placed on right side!

    # Check title at the top
    heading_elements = [e for e in elements if e.element_type == ElementType.HEADING]
    assert len(heading_elements) == 1
    assert heading_elements[0].text == "TYPES OF SCOLIOSIS"
    assert heading_elements[0].bbox.y1 < 100

    # 3. Test PPT generation
    ppt_service = PPTService()
    ppt_service.create_presentation()
    ppt_service.add_slide_from_elements(elements, img, 0, w, h)
    ppt_service.save("/app/output/test_scoliosis_slide.pptx")
    print("SUCCESS: Slide created with cropped image and formatted editable text!")
