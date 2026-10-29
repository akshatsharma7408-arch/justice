"""
JUSTICE Legal AI Backend — Ephemeral OCR Worker Subprocess
Invoked as: python -m app.services.ocr_worker <image_path>
Extracts text using RapidOCR in an isolated, transient child process.
Exits with code 0 and writes JSON output to stdout.
"""
import sys
import json
from pathlib import Path

# Ensure backend root is on sys.path
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.ocr_service import process_image_bytes_in_process

def main():
    if len(sys.argv) < 2:
        out = {"text": "[Error: Missing image file argument]", "is_unreadable": True, "confidence": 0.0, "error": "No file"}
        sys.stdout.write(json.dumps(out))
        sys.exit(1)

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        out = {"text": f"[Error: Image file not found: {image_path.name}]", "is_unreadable": True, "confidence": 0.0, "error": "Not found"}
        sys.stdout.write(json.dumps(out))
        sys.exit(1)

    try:
        raw_bytes = image_path.read_bytes()
        text, is_unreadable, conf = process_image_bytes_in_process(raw_bytes, image_path.name)
        out = {
            "text": text,
            "is_unreadable": is_unreadable,
            "confidence": round(conf, 3),
            "error": None
        }
        sys.stdout.write(json.dumps(out))
        sys.exit(0)
    except Exception as e:
        out = {
            "text": f"[Error: Exception during OCR processing: {e}]",
            "is_unreadable": True,
            "confidence": 0.0,
            "error": str(e)
        }
        sys.stdout.write(json.dumps(out))
        sys.exit(1)

if __name__ == "__main__":
    main()
