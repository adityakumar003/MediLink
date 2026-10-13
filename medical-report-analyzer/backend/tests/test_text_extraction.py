"""Unit and integration tests for text_extraction_service.py."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz  # PyMuPDF
import pytest
from PIL import Image, ImageDraw

from app.services import text_extraction_service
from app.services.offline_analysis_service import analyse_report_text_offline


@pytest.fixture
def sample_pdf_path() -> Path:
    return Path(__file__).parents[2] / "test_report_aditya.pdf"


@pytest.fixture
def digital_pdf(tmp_path: Path) -> Path:
    """Create a digital PDF with selectable text."""
    pdf_path = tmp_path / "digital.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 72),
        "Patient: John Doe\nHemoglobin: 14.2 g/dL 12.0-16.0 Normal\nGlucose: 95 mg/dL 70-100 Normal\n",
        fontsize=12,
    )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def scanned_pdf(tmp_path: Path) -> Path:
    """Create a scanned-like PDF containing only an image (no embedded text)."""
    pdf_path = tmp_path / "scanned.pdf"
    img = Image.new("RGB", (600, 400), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Hemoglobin: 13.5 g/dL Normal", fill="black")

    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    page.insert_image(page.rect, stream=img_bytes.getvalue())
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def mixed_pdf(tmp_path: Path) -> Path:
    """Create a 2-page PDF: Page 1 digital text, Page 2 image only."""
    pdf_path = tmp_path / "mixed.pdf"
    doc = fitz.open()

    # Page 1: Digital text
    page1 = doc.new_page(width=600, height=400)
    page1.insert_text((50, 50), "--- Clinic Report Page 1 ---\nPlatelets: 250 10^3/uL Normal", fontsize=12)

    # Page 2: Image only
    img = Image.new("RGB", (600, 400), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "WBC: 6.5 10^3/uL Normal", fill="black")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")

    page2 = doc.new_page(width=600, height=400)
    page2.insert_image(page2.rect, stream=img_bytes.getvalue())

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def sample_png(tmp_path: Path) -> Path:
    img_path = tmp_path / "report_photo.png"
    img = Image.new("RGB", (500, 300), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 40), "Cholesterol: 180 mg/dL Normal", fill="black")
    img.save(str(img_path))
    return img_path


@pytest.fixture
def sample_jpg(tmp_path: Path) -> Path:
    img_path = tmp_path / "report_photo.jpg"
    img = Image.new("RGB", (500, 300), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 40), "Creatinine: 0.9 mg/dL 0.6-1.2 Normal", fill="black")
    img.save(str(img_path))
    return img_path


# ── 1. Digital PDF extraction ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_digital_pdf(digital_pdf: Path) -> None:
    text = await text_extraction_service.extract_text(digital_pdf)
    assert "Hemoglobin" in text
    assert "14.2" in text
    assert "Glucose: 95 mg/dL" in text
    assert "--- Page 1 ---" in text


@pytest.mark.asyncio
async def test_extract_existing_sample_pdf(sample_pdf_path: Path) -> None:
    text = await text_extraction_service.extract_text(sample_pdf_path)
    assert len(text) > 50
    assert "--- Page 1 ---" in text


# ── 2. Scanned PDF extraction (with mocked/real OCR) ──────────────────────

@pytest.mark.asyncio
async def test_extract_scanned_pdf(scanned_pdf: Path) -> None:
    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [
        [
            [[[50, 50], [200, 50], [200, 70], [50, 70]], ("Hemoglobin: 13.5 g/dL Normal", 0.98)]
        ]
    ]

    with patch.object(text_extraction_service, "get_ocr_engine", return_value=mock_engine):
        text = await text_extraction_service.extract_text(scanned_pdf)

    assert "Hemoglobin: 13.5 g/dL Normal" in text
    assert "--- Page 1 ---" in text


# ── 3. Image extraction (JPG and PNG) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_from_png(sample_png: Path) -> None:
    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [
        [
            [[[40, 40], [220, 40], [220, 60], [40, 60]], ("Cholesterol: 180 mg/dL Normal", 0.95)]
        ]
    ]

    with patch.object(text_extraction_service, "get_ocr_engine", return_value=mock_engine):
        text = await text_extraction_service.extract_text(sample_png)

    assert "Cholesterol: 180 mg/dL Normal" in text
    assert "--- Page 1 ---" in text


@pytest.mark.asyncio
async def test_extract_from_jpg(sample_jpg: Path) -> None:
    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [
        [
            [[[40, 40], [300, 40], [300, 60], [40, 60]], ("Creatinine: 0.9 mg/dL 0.6-1.2 Normal", 0.96)]
        ]
    ]

    with patch.object(text_extraction_service, "get_ocr_engine", return_value=mock_engine):
        text = await text_extraction_service.extract_text(sample_jpg)

    assert "Creatinine: 0.9 mg/dL 0.6-1.2 Normal" in text


# ── 4. Mixed PDFs (Digital + Scanned pages) ────────────────────────────────

@pytest.mark.asyncio
async def test_extract_mixed_pdf(mixed_pdf: Path) -> None:
    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [
        [
            [[[50, 50], [250, 50], [250, 70], [50, 70]], ("WBC: 6.5 10^3/uL Normal", 0.97)]
        ]
    ]

    with patch.object(text_extraction_service, "get_ocr_engine", return_value=mock_engine):
        text = await text_extraction_service.extract_text(mixed_pdf)

    # Both page 1 (digital) and page 2 (OCR) should be present in order
    assert "--- Page 1 ---" in text
    assert "Platelets" in text
    assert "--- Page 2 ---" in text
    assert "WBC: 6.5" in text


# ── 5. Empty PDFs and blank image files ─────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_blank_pdf(tmp_path: Path) -> None:
    blank_pdf = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=500, height=500)  # Blank page
    doc.save(str(blank_pdf))
    doc.close()

    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [[]]  # OCR finds nothing

    with patch.object(text_extraction_service, "get_ocr_engine", return_value=mock_engine):
        with pytest.raises(ValueError, match="Could not extract meaningful text"):
            await text_extraction_service.extract_text(blank_pdf)


@pytest.mark.asyncio
async def test_blank_image(tmp_path: Path) -> None:
    blank_img = tmp_path / "blank.png"
    Image.new("RGB", (100, 100), color="white").save(str(blank_img))

    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [[]]

    with patch.object(text_extraction_service, "get_ocr_engine", return_value=mock_engine):
        with pytest.raises(ValueError, match="No readable text could be detected"):
            await text_extraction_service.extract_text(blank_img)


# ── 6. Corrupted, encrypted, and unsupported files ─────────────────────────

@pytest.mark.asyncio
async def test_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        await text_extraction_service.extract_text("nonexistent_report.pdf")


@pytest.mark.asyncio
async def test_unsupported_file_extension(tmp_path: Path) -> None:
    bad_file = tmp_path / "report.docx"
    bad_file.write_text("Hello world")
    with pytest.raises(ValueError, match="Unsupported file format"):
        await text_extraction_service.extract_text(bad_file)


@pytest.mark.asyncio
async def test_corrupted_pdf(tmp_path: Path) -> None:
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-not-really-valid-content")
    with pytest.raises(ValueError, match="Failed to open PDF file"):
        await text_extraction_service.extract_text(corrupt_pdf)


@pytest.mark.asyncio
async def test_corrupted_image(tmp_path: Path) -> None:
    corrupt_img = tmp_path / "corrupt.jpg"
    corrupt_img.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="Unreadable or corrupted image file"):
        await text_extraction_service.extract_text(corrupt_img)


# ── 7. PaddleOCR engine unavailable or inference failure ──────────────────

@pytest.mark.asyncio
async def test_ocr_engine_unavailable_for_image(sample_png: Path) -> None:
    with patch.object(text_extraction_service, "get_ocr_engine", return_value=None):
        with pytest.raises(ValueError, match="PaddleOCR engine is unavailable"):
            await text_extraction_service.extract_text(sample_png)


@pytest.mark.asyncio
async def test_ocr_inference_error_for_scanned_pdf(scanned_pdf: Path) -> None:
    mock_engine = MagicMock()
    mock_engine.ocr.side_effect = RuntimeError("Paddle internal memory error")

    with patch.object(text_extraction_service, "get_ocr_engine", return_value=mock_engine):
        # Should raise ValueError because no text could be extracted
        with pytest.raises(ValueError, match="Could not extract meaningful text"):
            await text_extraction_service.extract_text(scanned_pdf)


# ── 8. Compatibility with downstream medical analysis pipeline ─────────────

@pytest.mark.asyncio
async def test_extracted_text_compatible_with_offline_analysis(digital_pdf: Path) -> None:
    extracted = await text_extraction_service.extract_text(digital_pdf)
    analysis = analyse_report_text_offline(extracted)

    assert "parameters" in analysis
    param_names = [p["name"].lower() for p in analysis["parameters"]]
    assert any("hemoglobin" in name for name in param_names)
    assert any("glucose" in name for name in param_names)
    assert "disease_risks" in analysis
