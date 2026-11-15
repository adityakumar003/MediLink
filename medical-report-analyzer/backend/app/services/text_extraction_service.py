"""
app/services/text_extraction_service.py
────────────────────────────────────────
PDF and image text extraction with a pluggable extractor strategy.

Extraction strategies:
  1. PyMuPDF (fitz) - Primary extractor for digitally generated PDFs with text layer.
  2. PaddleOCR      - OCR engine for scanned PDF pages and uploaded images.

Public API:
    extract_text(file_path: str | Path) -> str

Supported formats:
    • PDF (.pdf) - Digital, scanned, or mixed page PDFs.
    • Images (.jpg, .jpeg, .png) - Scanned / photo medical documents.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

# Per-page character count threshold to consider a page as having sufficient digital text.
# Pages with fewer characters are treated as scanned / image-only and sent to PaddleOCR.
MIN_PAGE_TEXT_LENGTH: int = 40

# Supported image file extensions
SUPPORTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png"})

# DPI for rendering PDF pages to image before OCR inference (300 DPI gives clean OCR)
RENDER_DPI: int = 300

# PaddleOCR leaves small text on the table unless detection keeps native detail:
# the default limit (960 px) downscales typical 300-DPI scans. 1920 preserves it.
OCR_DET_LIMIT_SIDE_LEN: int = 1920
OCR_DET_LIMIT_TYPE: str = "max"
# Keep faint / low-contrast text instead of discarding it as low confidence.
OCR_DROP_SCORE: float = 0.3
OCR_DET_BOX_THRESH: float = 0.3
# Upscale small scans before OCR so small table text stays legible.
OCR_MIN_WIDTH: int = 1600

# OCR Engine Singleton
_ocr_engine: Optional[Any] = None
_ocr_init_failed: bool = False


def get_ocr_engine() -> Optional[Any]:
    """
    Return a lazily initialized PaddleOCR singleton.
    Enforces CPU-only execution and caches the engine instance.
    Returns None if PaddleOCR is not installed or fails to initialize.
    """
    global _ocr_engine, _ocr_init_failed

    if _ocr_engine is not None:
        return _ocr_engine

    if _ocr_init_failed:
        return None

    try:
        # PaddlePaddle 2.x ships generated protobuf code incompatible with
        # protobuf>=4 (raises "Descriptors cannot be created directly").
        # Downgrading protobuf would break google-genai, so force protobuf's
        # pure-Python implementation for the OCR stack instead. This affects
        # only protobuf message parsing (one-time import cost); tensor math
        # stays native. Proper fix: upgrade to PaddlePaddle/PaddleOCR 3.x.
        import os as _os

        _os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
        from paddleocr import PaddleOCR  # type: ignore[import]

        logger.info("Initializing PaddleOCR engine (lang='en', CPU)...")
        _ocr_engine = PaddleOCR(
            use_angle_cls=True,  # Handle rotated/skewed orientation
            lang="en",           # English recognition model
            use_gpu=False,       # CPU inference only
            show_log=False,      # Suppress verbose paddle logging
            det_limit_side_len=OCR_DET_LIMIT_SIDE_LEN,
            det_limit_type=OCR_DET_LIMIT_TYPE,
            drop_score=OCR_DROP_SCORE,
            det_db_box_thresh=OCR_DET_BOX_THRESH,
        )
        logger.info("PaddleOCR engine initialized successfully.")
        return _ocr_engine

    except ImportError:
        logger.warning(
            "PaddleOCR or PaddlePaddle is not installed. Scanned PDF & image OCR is unavailable."
        )
        _ocr_init_failed = True
        return None
    except Exception as exc:
        logger.error("Failed to initialize PaddleOCR engine: %s", exc)
        _ocr_init_failed = True
        return None


# ── Public API ─────────────────────────────────────────────────────────────

async def extract_text(file_path: str | Path) -> str:
    """
    Extract text from a medical report PDF or image file.

    PDF Strategy:
      1. Use PyMuPDF to extract text page-by-page.
      2. If a page has insufficient text (< MIN_PAGE_TEXT_LENGTH), render the page
         to an image and use PaddleOCR to extract text.
      3. Combine extracted text preserving original page order and layout.

    Image Strategy (.jpg, .jpeg, .png):
      1. Validate file readability.
      2. Run PaddleOCR directly.
      3. Return structured text.

    Args:
        file_path: Absolute or relative path to PDF or image file.

    Returns:
        Extracted plain text formatted by page.

    Raises:
        FileNotFoundError: If the target file does not exist.
        ValueError: If file is empty, corrupted, encrypted, unsupported, or has no extractable text.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()

    if ext == ".pdf":
        return await _extract_from_pdf(path)
    elif ext in SUPPORTED_IMAGE_EXTENSIONS:
        return _extract_from_image(path)
    else:
        raise ValueError(
            f"Unsupported file format '{ext}'. Accepted formats are PDF (.pdf) and images (.jpg, .jpeg, .png)."
        )


# ── PDF Extraction ──────────────────────────────────────────────────────────

async def _extract_from_pdf(path: Path) -> str:
    """
    Extract text from a PDF file using PyMuPDF for digital pages
    and PaddleOCR for scanned/image pages.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ValueError("PyMuPDF is not installed. Run `pip install PyMuPDF`.") from exc

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise ValueError(
            f"Failed to open PDF file '{path.name}'. The file may be corrupted or invalid: {exc}"
        ) from exc

    try:
        if doc.is_encrypted:
            raise ValueError(f"The PDF file '{path.name}' is password-protected or encrypted.")

        if doc.page_count == 0:
            raise ValueError(f"The PDF file '{path.name}' contains no pages.")

        page_texts: List[Tuple[int, str]] = []

        for page_num, page in enumerate(doc, start=1):
            digital_text = page.get_text("text") or ""
            stripped_digital = digital_text.strip()

            if len(stripped_digital) >= MIN_PAGE_TEXT_LENGTH:
                # Digital page with sufficient text
                page_texts.append((page_num, stripped_digital))
                logger.info("Page %d: Extracted %d chars via PyMuPDF.", page_num, len(stripped_digital))
            else:
                # Page has insufficient text (likely scanned or image-based)
                logger.info(
                    "Page %d: Insufficient embedded text (%d chars). Falling back to PaddleOCR...",
                    page_num,
                    len(stripped_digital),
                )
                ocr_text = _ocr_pdf_page(page, page_num)
                if ocr_text:
                    page_texts.append((page_num, ocr_text))
                    logger.info("Page %d: Extracted %d chars via PaddleOCR.", page_num, len(ocr_text))
                elif stripped_digital:
                    # OCR returned nothing, but we had a small amount of digital text; keep it
                    page_texts.append((page_num, stripped_digital))
                    logger.info("Page %d: OCR yielded no text; retained %d chars from digital layer.", page_num, len(stripped_digital))

        if not page_texts:
            raise ValueError(
                f"Could not extract meaningful text from PDF '{path.name}'. "
                "The document may be blank, unreadable, or contain unsupported graphics."
            )

        # Assemble full document text with clear page markers
        assembled = "\n\n".join(f"--- Page {num} ---\n{text}" for num, text in page_texts)
        return assembled

    finally:
        doc.close()


def _ocr_pdf_page(page: Any, page_num: int) -> str:
    """
    Render a PyMuPDF page to an image and run PaddleOCR text recognition.
    """
    engine = get_ocr_engine()
    if engine is None:
        logger.warning(
            "Page %d: PaddleOCR engine unavailable; skipping OCR for scanned page.", page_num
        )
        return ""

    temp_path: Optional[str] = None
    try:
        import fitz

        zoom = RENDER_DPI / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_path = temp_file.name

        pixmap.save(temp_path)
        return _run_ocr_on_file(temp_path, engine)

    except Exception as exc:
        logger.warning("OCR processing failed on page %d: %s", page_num, exc)
        return ""
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


# ── Image Extraction ────────────────────────────────────────────────────────

def _extract_from_image(path: Path) -> str:
    """
    Extract text directly from an image file (JPG, JPEG, PNG) using PaddleOCR.
    """
    try:
        from PIL import Image

        with Image.open(str(path)) as img:
            img.verify()
    except Exception as exc:
        raise ValueError(f"Unreadable or corrupted image file '{path.name}': {exc}") from exc

    engine = get_ocr_engine()
    if engine is None:
        raise ValueError(
            "PaddleOCR engine is unavailable. "
            "Install paddlepaddle and paddleocr to process image files."
        )

    text = _run_ocr_on_file(str(path), engine)
    if not text:
        raise ValueError(
            f"No readable text could be detected in image '{path.name}'. "
            "Please ensure the image is clear and contains readable text."
        )

    logger.info("Image '%s': Extracted %d chars via PaddleOCR.", path.name, len(text))
    return f"--- Page 1 ---\n{text}"


# ── OCR Helper & Layout Preservation ────────────────────────────────────────

def _prepare_ocr_image(image_path: str) -> Optional[str]:
    """
    Return a temporary enhanced copy of an image for OCR, or None.

    Low-resolution, low-contrast, and blurry scans lose small table text:
      1. Upscale narrow images to OCR_MIN_WIDTH so small glyphs stay legible.
      2. Normalise contrast (CLAHE when OpenCV is available) and sharpen.

    The caller owns the returned file and must delete it.
    """
    temp_path: Optional[str] = None
    try:
        from PIL import Image, ImageFilter, ImageOps

        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")

            if image.width < OCR_MIN_WIDTH:
                scale = OCR_MIN_WIDTH / float(image.width)
                new_size = (
                    int(round(image.width * scale)),
                    int(round(image.height * scale)),
                )
                image = image.resize(new_size, Image.LANCZOS)

            try:
                import cv2  # Installed with PaddleOCR; optional for preprocessing.
                import numpy as np

                gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
                gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
                blurred = cv2.GaussianBlur(gray, (0, 0), 3.0)
                enhanced = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)
                output = Image.fromarray(enhanced)
            except Exception:
                output = ImageOps.autocontrast(image.convert("L"))
                output = output.filter(
                    ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3)
                )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_path = temp_file.name
        output.save(temp_path, "PNG")
        return temp_path

    except Exception as exc:
        logger.debug("Image preprocessing skipped for '%s': %s", image_path, exc)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return None


def _run_ocr_on_file(image_path: str, engine: Any) -> str:
    """
    Run PaddleOCR on an image file and return ordered, line-preserved text.
    Sorts bounding boxes top-to-bottom and left-to-right to preserve
    table rows, parameters, and clinical reading order.
    """
    prepared_path = _prepare_ocr_image(image_path)
    ocr_path = prepared_path or image_path
    try:
        result = engine.ocr(ocr_path, cls=True)
    except Exception as exc:
        logger.warning("PaddleOCR inference error on '%s': %s", image_path, exc)
        return ""
    finally:
        if prepared_path and os.path.exists(prepared_path):
            try:
                os.remove(prepared_path)
            except OSError:
                pass

    if not result or not result[0]:
        return ""

    detections = []
    for item in result[0]:
        try:
            box = item[0]        # [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
            text, score = item[1]
            text = text.strip()
            if text:
                # Compute center y and center x for line sorting
                ys = [pt[1] for pt in box]
                xs = [pt[0] for pt in box]
                cy = sum(ys) / len(ys)
                cx = sum(xs) / len(xs)
                height = max(ys) - min(ys)
                detections.append({
                    "text": text,
                    "cx": cx,
                    "cy": cy,
                    "height": height,
                    "score": score,
                })
        except (IndexError, TypeError, ValueError):
            continue

    if not detections:
        return ""

    # Sort boxes primarily top-to-bottom
    detections.sort(key=lambda d: d["cy"])

    # Group into lines based on vertical overlap/height tolerance
    lines: List[List[dict]] = []
    for det in detections:
        if not lines:
            lines.append([det])
            continue

        last_line = lines[-1]
        line_avg_cy = sum(d["cy"] for d in last_line) / len(last_line)
        line_avg_h = sum(d["height"] for d in last_line) / len(last_line)
        v_tolerance = max(line_avg_h * 0.5, 10.0)

        if abs(det["cy"] - line_avg_cy) <= v_tolerance:
            last_line.append(det)
        else:
            lines.append([det])

    # For each line, sort tokens left-to-right
    formatted_lines: List[str] = []
    for line in lines:
        line.sort(key=lambda d: d["cx"])
        formatted_lines.append("  ".join(d["text"] for d in line))

    return "\n".join(formatted_lines)
