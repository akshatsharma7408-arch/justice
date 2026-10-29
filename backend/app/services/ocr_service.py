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
import os
import threading
import gc
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from app.services.llm_service import clean_ocr_noise

logger = logging.getLogger("justice.ocr")

# Lazy-loaded RapidOCR engine instance
_RAPID_OCR_ENGINE = None
_OCR_LOCK = threading.Lock()

# Measured OCR worker peak RSS ~600-700MB regardless of input size (ONNX runtime overhead).
# Never spawn the worker when the instance plausibly lacks that headroom: on a shared cgroup
# the OOM killer can terminate the WEB process, not just the child.
DEFAULT_OCR_WORKER_PEAK_MB = 768


def _ocr_memory_status(peak_mb: int = None, reserve_mb: int = None) -> str:
    """Returns "ok", "contention", or "capacity" for running an OCR worker of the given
    peak footprint now. Defaults to the RapidOCR worker's measured peak.
    "capacity" = the instance's memory limit itself is below the worker peak plus
    a baseline reserve for the web process (a fixed plan limit; retrying soon will not help).
    "contention" = the limit is sufficient but current usage leaves too little headroom now.
    Prefers cgroup limits (containers) over host /proc/meminfo."""
    if peak_mb is None:
        peak_mb = int(os.environ.get("JUSTICE_OCR_WORKER_PEAK_MB", str(DEFAULT_OCR_WORKER_PEAK_MB)))
    if reserve_mb is None:
        reserve_mb = int(os.environ.get("JUSTICE_OCR_RESERVE_MB", "256"))
    need = peak_mb * 1024 * 1024
    try:
        v2_max = "/sys/fs/cgroup/memory.max"
        v2_cur = "/sys/fs/cgroup/memory.current"
        if os.path.exists(v2_max) and os.path.exists(v2_cur):
            raw = open(v2_max).read().strip()
            if raw != "max":
                limit = int(raw)
                if limit < (peak_mb + reserve_mb) * 1024 * 1024:
                    return "capacity"
                current = int(open(v2_cur).read().strip())
                return "ok" if (limit - current) >= need else "contention"
        v1_max = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
        v1_cur = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
        if os.path.exists(v1_max) and os.path.exists(v1_cur):
            limit = int(open(v1_max).read().strip())
            if limit < (1 << 60):  # huge sentinel means "no limit"
                if limit < (peak_mb + reserve_mb) * 1024 * 1024:
                    return "capacity"
                current = int(open(v1_cur).read().strip())
                return "ok" if (limit - current) >= need else "contention"
        total = avail = None
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) * 1024
        if total is not None and total < (peak_mb + reserve_mb) * 1024 * 1024:
            return "capacity"
        if avail is not None:
            return "ok" if avail >= need else "contention"
    except Exception:
        pass
    return "ok"  # undetectable limits: do not block local/dev usage


def _memory_allows_ocr() -> bool:
    return _ocr_memory_status() == "ok"


# Tesseract fallback engine: measured peak RSS ~132MB OCRing a dense 300 DPI
# two-column Gazette page (~14s/page); far lighter than the RapidOCR ONNX worker
# (~600-700MB). Used when the RapidOCR worker is memory-blocked or unavailable.
TESSERACT_PEAK_MB_DEFAULT = 192
TESSERACT_TIMEOUT_S = 90


def _tesseract_status() -> str:
    """Memory status for the tesseract fallback worker."""
    peak = int(os.environ.get("JUSTICE_TESSERACT_PEAK_MB", str(TESSERACT_PEAK_MB_DEFAULT)))
    return _ocr_memory_status(peak_mb=peak, reserve_mb=64)


def _tesseract_available() -> bool:
    import shutil
    return shutil.which("tesseract") is not None


def _process_image_bytes_tesseract(image_bytes: bytes, filename: str = "image.png") -> Tuple[str, bool, float]:
    """
    OCR one image via the tesseract CLI (subprocess, tsv output for real confidence).
    Returns (text, is_unreadable, confidence) in the same 0-1 confidence scale as RapidOCR.
    """
    import subprocess
    import tempfile

    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        logger.warning(f"Tesseract: failed to open image '{filename}': {e}")
        return f"[Error: Could not read image format for '{filename}']", True, 0.0

    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Bound input size: keeps tesseract memory/time predictable
    max_dim = 1600
    if max(img.width, img.height) > max_dim:
        scale = max_dim / float(max(img.width, img.height))
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.LANCZOS)
    img = img.convert("L")

    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img.save(f.name, format="PNG")
            tmp_file = f.name
        del img
        gc.collect()

        proc = subprocess.run(
            ["tesseract", tmp_file, "stdout", "-l", "eng", "tsv"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TESSERACT_TIMEOUT_S,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore").strip()[:200]
            logger.warning(f"Tesseract failed on '{filename}': {err}")
            return f"[Error: OCR processing failed on '{filename}']", True, 0.0

        tsv = proc.stdout.decode("utf-8", errors="ignore")
        words, confs = [], []
        for line in tsv.splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) == 12:
                try:
                    conf = float(cols[10])
                except ValueError:
                    continue
                text = cols[11].strip()
                if text and conf >= 0:
                    words.append(text)
                    confs.append(conf)
        combined_raw = " ".join(words).strip()
        avg_score = (sum(confs) / len(confs) / 100.0) if confs else 0.0

        if avg_score < 0.30 or len(combined_raw) < 20:
            logger.warning(f"Tesseract flagged '{filename}' blurry/unreadable (score={avg_score:.2f}, chars={len(combined_raw)})")
            return "This image is too blurry or unclear to read reliably. Please upload a clearer photo.", True, avg_score

        cleaned = clean_ocr_noise(combined_raw)
        return cleaned, False, avg_score
    except subprocess.TimeoutExpired:
        logger.error(f"Tesseract timed out after {TESSERACT_TIMEOUT_S}s on '{filename}'")
        return f"[Error: OCR processing timed out on '{filename}']", True, 0.0
    except Exception as e:
        logger.error(f"Tesseract fallback error on '{filename}': {e}")
        return f"[Error: OCR processing failed on '{filename}']", True, 0.0
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


def _memory_blocked_response(image_bytes: bytes, filename: str, mem_status: str) -> Tuple[str, bool, float]:
    """
    RapidOCR is memory-blocked. Try the lighter tesseract engine before giving up;
    only return the capacity/contention error when no engine can run.
    """
    if _tesseract_available() and _tesseract_status() == "ok":
        logger.info(f"RapidOCR memory status={mem_status}; using tesseract fallback for '{filename}'.")
        return _process_image_bytes_tesseract(image_bytes, filename)
    if mem_status == "capacity":
        return ("[Error: OCR capacity: document/image text extraction is unavailable on this server's "
                "current memory plan]", True, 0.0)
    return ("[Error: OCR contention: OCR is temporarily unavailable due to current server memory pressure]",
            True, 0.0)


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


def process_image_bytes_in_process(image_bytes: bytes, filename: str = "image.png") -> Tuple[str, bool, float]:
    """
    Direct in-process image OCR inference using RapidOCR engine.
    Called inside worker subprocess or as direct fallback.
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

    # 2. Resize to max 1024px on longest side (strict memory limit)
    max_dim = 1024
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
        if _tesseract_available():
            logger.warning(f"RapidOCR engine unavailable; using tesseract for '{filename}'.")
            return _process_image_bytes_tesseract(image_bytes, filename)
        return "[Error: OCR engine is currently unavailable]", True, 0.0

    try:
        with _OCR_LOCK:
            results, _ = engine(np_img)
    except Exception as e:
        logger.error(f"RapidOCR execution failed on '{filename}': {e}")
        return f"[Error: OCR processing error on '{filename}']", True, 0.0
    finally:
        del rgb_img
        del np_img
        del img
        gc.collect()

    if not results:
        return "This image is too blurry or unclear to read reliably. Please upload a clearer photo.", True, 0.0

    # Extract lines and scores
    lines = []
    scores = []
    for item in results:
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


def process_image_bytes(image_bytes: bytes, filename: str = "image.png") -> Tuple[str, bool, float]:
    """
    Processes a single image via an ephemeral isolated subprocess to prevent ONNX Runtime
    native memory pools from accumulating inside the main server process.
    Falls back gracefully to in-process OCR if subprocess spawning fails.
    """
    import os
    import sys
    import subprocess
    import tempfile
    import json
    from pathlib import Path

    # If already running inside an ocr_worker subprocess, run in-process directly to avoid recursion
    if "ocr_worker" in sys.argv[0]:
        return process_image_bytes_in_process(image_bytes, filename)

    tmp_file = None
    try:
        suffix = os.path.splitext(filename)[1] or ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(image_bytes)
            tmp_file = f.name

        mem_status = _ocr_memory_status()
        if mem_status != "ok":
            logger.warning(f"RapidOCR blocked for '{filename}': memory status={mem_status}.")
            return _memory_blocked_response(image_bytes, filename, mem_status)

        env = os.environ.copy()
        backend_dir = str(Path(__file__).resolve().parent.parent.parent)
        env["PYTHONPATH"] = backend_dir

        cmd = [sys.executable, "-m", "app.services.ocr_worker", tmp_file]
        with _OCR_LOCK:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=25.0)
            except subprocess.TimeoutExpired:
                logger.error(f"OCR subprocess timed out after 25s for '{filename}'")
                proc.kill()
                proc.communicate()
                return f"[Error: OCR processing timed out on '{filename}']", True, 0.0

            if proc.returncode != 0:
                err_msg = stderr_bytes.decode("utf-8", errors="ignore").strip()
                logger.warning(f"OCR worker returned non-zero code {proc.returncode} for '{filename}': {err_msg}")
                if stdout_bytes:
                    try:
                        res = json.loads(stdout_bytes.decode("utf-8"))
                        return res.get("text", ""), res.get("is_unreadable", True), res.get("confidence", 0.0)
                    except Exception:
                        pass
                return f"[Error: OCR processing failed on '{filename}']", True, 0.0

            res = json.loads(stdout_bytes.decode("utf-8"))
            return res.get("text", ""), res.get("is_unreadable", False), res.get("confidence", 0.0)

    except Exception as e:
        fb_status = _ocr_memory_status()
        if fb_status != "ok":
            logger.warning(f"OCR subprocess failed ({e}) and memory status={fb_status}; trying tesseract for '{filename}'.")
            return _memory_blocked_response(image_bytes, filename, fb_status)
        if _tesseract_available():
            logger.warning(f"OCR subprocess execution encountered exception: {e}; trying tesseract fallback.")
            text, unreadable, conf = _process_image_bytes_tesseract(image_bytes, filename)
            if not unreadable or not str(text).startswith("[Error"):
                return text, unreadable, conf
        logger.warning(f"Falling back to in-process OCR for '{filename}'.")
        return process_image_bytes_in_process(image_bytes, filename)
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


def process_multi_images(images: List[Tuple[str, bytes]]) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Processes up to 10 images in order:
    Returns (concatenated_text, page_metadata, warnings).
    Includes structured outcome status per page.
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
            "is_unreadable": is_unreadable,
            "status": "FAILED" if is_unreadable else "SUCCESS",
            "error_reason": page_text if is_unreadable else None
        })
        gc.collect()

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
