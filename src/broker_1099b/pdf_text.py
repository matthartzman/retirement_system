"""PDF text-layer extraction for broker statements. ``pypdf`` is an OPTIONAL import: nothing here imports it at
module load, so the app runs without it and the text path never needs it."""
from __future__ import annotations

import io


class PdfUnavailable(Exception):
    """pypdf is not installed."""


class PdfUnreadable(Exception):
    """The bytes are not a readable PDF, or the PDF has no text layer."""


def _import_pypdf():
    try:
        import pypdf  # noqa: PLC0415  (optional dependency)
    except ImportError:
        return None
    return pypdf


def extract_text(data: bytes) -> str:
    pypdf = _import_pypdf()
    if pypdf is None:
        raise PdfUnavailable("PDF import needs the optional 'pypdf' package (pip install pypdf); "
                             "alternatively paste the statement text.")
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception as exc:  # pypdf raises several error types for damaged files
        raise PdfUnreadable(f"Could not read the PDF: {exc}") from exc
    text = "\n".join(pages)
    if not text.strip():
        raise PdfUnreadable("The PDF has no extractable text layer (image-only pages need OCR, which is not supported).")
    return text
