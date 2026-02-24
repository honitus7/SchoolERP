from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytesseract


def extract_lines(file_path: str) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        return []

    text = pytesseract.image_to_string(Image.open(path))
    return [line.strip() for line in text.splitlines() if line.strip()]
