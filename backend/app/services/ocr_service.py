"""
JUSTICE Legal AI Backend — OCR & Multi-Image Document Service
Handles multi-image contract uploads (PDF, DOCX, TXT, JPG, PNG, WEBP, HEIC):
1. EXIF auto-rotation (PIL ImageOps.exif_transpose)
2. Resize max 2000px on longest side (preserves aspect ratio, prevents timeouts)
3. RapidOCR pipeline
4. Blurry / unreadable detection (confidence < 0.3 or characters < 20)
5. OCR noise cleanup
"""

import io
import logging
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image, ImageOps

from app.services.llm_service import clean_ocr_noise

logger = logging.getLogger("justice.ocr")

# Lazy-loaded RapidOCR engine instance
_RAPID_OCR_ENGINE = None

def get_ocr_engine():
    global _RAPID_OCR_ENGINE
    if _RAPID_OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID_OCR_ENGINE = RapidOCR()
            logger.info("RapidOCR engine initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize RapidOCR engine: {e}")
            _RAPID_OCR_ENGINE = None
    return _RAPID_OCR_ENGINE


def process_image_bytes(image_bytes: bytes, filename: str = "image.png") -> Tuple[str, bool, float]:
    """
    Processes a single image:
    Returns (extracted_text, is_unreadable, avg_confidence).
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        logger.warning(f"Failed to open image '{filename}': {e}")
        return f"[Error: Could not read image format for '{filename}']", True, 0.0

    # 1. EXIF auto-rotation
    try:
        img = ImageOps.exif_transpose(img)
    except Exception as e:
        logger.debug(f"EXIF transpose skipped: {e}")

    # 2. Resize to max 2000px on longest side
    max_dim = 2000
    if max(img.width, img.height) > max_dim:
        scale = max_dim / float(max(img.width, img.height))
        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # 3. Convert to RGB numpy array
    rgb_img = img.convert("RGB")
    np_img = np.array(rgb_img)

    # 4. RapidOCR inference
    engine = get_ocr_engine()
    if not engine:
        return "[Error: OCR engine is currently unavailable]", True, 0.0

    try:
        results, _ = engine(np_img)
    except Exception as e:
        logger.error(f"RapidOCR execution failed on '{filename}': {e}")
        return f"[Error: OCR processing error on '{filename}']", True, 0.0

    if not results:
        return "This image is too blurry or unclear to read reliably. Please upload a clearer photo.", True, 0.0

    # Extract lines and scores
    lines = []
    scores = []
    for item in results:
        # RapidOCR format: [box, text, score]
        if len(item) >= 3:
            text = str(item[1]).strip()
            score = float(item[2])
            if text:
                lines.append(text)
                scores.append(score)

    avg_score = (sum(scores) / len(scores)) if scores else 0.0
    combined_raw = "\n".join(lines).strip()

    # 5. Check readability
    if avg_score < 0.30 or len(combined_raw) < 20:
        logger.warning(f"Image '{filename}' flagged as blurry/unreadable (score={avg_score:.2f}, chars={len(combined_raw)})")
        return "This image is too blurry or unclear to read reliably. Please upload a clearer photo.", True, avg_score

    # 6. Clean OCR noise
    cleaned = clean_ocr_noise(combined_raw)
    return cleaned, False, avg_score


def process_multi_images(images: List[Tuple[str, bytes]]) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Processes up to 10 images in order:
    Returns (concatenated_text, page_metadata, warnings).
    """
    pages_text = []
    pages_meta = []
    warnings = []

    for idx, (fname, raw_bytes) in enumerate(images[:10]):
        page_num = idx + 1
        page_text, is_unreadable, conf = process_image_bytes(raw_bytes, fname)

        if is_unreadable:
            warnings.append(f"Page {page_num} ({fname}): {page_text}")
            formatted_page = f"--- Page {page_num} ({fname}) ---\n[Warning: {page_text}]"
        else:
            formatted_page = f"--- Page {page_num} ({fname}) ---\n{page_text}"

        pages_text.append(formatted_page)
        pages_meta.append({
            "page": page_num,
            "filename": fname,
            "char_count": len(page_text),
            "confidence": round(conf, 3),
            "is_unreadable": is_unreadable
        })

    full_text = "\n\n".join(pages_text)
    return full_text, pages_meta, warnings


def extract_text_from_pdf_with_ocr_fallback(file_bytes: bytes) -> Tuple[str, List[str]]:
    """
    Extracts text from PDF. If pages are scanned (empty embedded text),
    renders pages as images using PyMuPDF and runs RapidOCR.
    """
    warnings = []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages_text = []

        for i, page in enumerate(doc):
            page_num = i + 1
            txt = page.get_text().strip()
            if len(txt) >= 40:
                pages_text.append(f"--- Page {page_num} ---\n{txt}")
            else:
                # Scanned page fallback: render pixmap and run OCR
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                ocr_txt, is_unreadable, conf = process_image_bytes(img_bytes, f"pdf_page_{page_num}.png")
                if is_unreadable:
                    warnings.append(f"Page {page_num}: {ocr_txt}")
                    pages_text.append(f"--- Page {page_num} ---\n[Warning: {ocr_txt}]")
                else:
                    pages_text.append(f"--- Page {page_num} ---\n{ocr_txt}")

        full_doc = "\n\n".join(pages_text).strip()
        return full_doc, warnings
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed: {e}. Falling back to pypdf.")
        from app.routers.audit import extract_text_from_pdf
        return extract_text_from_pdf(file_bytes), warnings
