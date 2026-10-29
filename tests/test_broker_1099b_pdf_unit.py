"""PDF text step of the 1099-B import (plan step 5.1): pypdf is an optional import."""
from __future__ import annotations

import importlib

import pytest

import broker_1099b_synthetic as syn
from src import broker_1099b
from src.broker_1099b import pdf_text

SYMBOLS = {"ABCD", "WXYZ", "QRST", "LMNO", "PQRS"}


def make_pdf(lines_per_page: list[list[str]]) -> bytes:
    """A minimal text-layer PDF (one Helvetica text line per row) built by hand, so no PDF writer is needed."""
    objs: list[bytes] = []
    n_pages = len(lines_per_page)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    font_obj = 3 + 2 * n_pages
    for i, lines in enumerate(lines_per_page):
        content = ["BT", "/F1 7 Tf", "8 TL", "20 780 Td"]
        for ln in lines:
            esc = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content.append(f"({esc}) Tj T*")
        content.append("ET")
        stream = "\n".join(content).encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1000 800] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {font_obj} 0 R >> >> >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def statement_pdf() -> bytes:
    lines = syn.build_statement().splitlines()
    return make_pdf([lines[i:i + 18] for i in range(0, len(lines), 18)])


def test_extract_text_round_trips_the_statement():
    pytest.importorskip("pypdf")
    text = pdf_text.extract_text(statement_pdf())
    assert "CUSIP: 111111111 Symbol: ABCDAlpha Beta Corp Class A" in text
    assert "03/04/25 09/10/25 1,500.00 1,400.00" in text


def test_pdf_preview_ties_out_end_to_end():
    pytest.importorskip("pypdf")
    pv = broker_1099b.preview_statement("etrade", pdf_bytes=statement_pdf(), known_symbols=SYMBOLS)
    assert pv["errors"] == [], pv["errors"]
    assert pv["received"] == 7 and pv["can_apply"] is True and pv["source_format"] == "pdf"


def test_missing_pypdf_is_a_clean_preview_error_not_a_crash(monkeypatch):
    monkeypatch.setattr(pdf_text, "_import_pypdf", lambda: None)
    pv = broker_1099b.preview_statement("etrade", pdf_bytes=b"%PDF-1.4", known_symbols=SYMBOLS)
    assert pv["can_apply"] is False and pv["will_write"] == [] and pv["received"] == 0
    assert any("pypdf" in e["error"] for e in pv["errors"])


def test_text_path_does_not_need_pypdf(monkeypatch):
    monkeypatch.setattr(pdf_text, "_import_pypdf", lambda: None)
    pv = broker_1099b.preview_statement("etrade", text=syn.build_statement(), known_symbols=SYMBOLS)
    assert pv["can_apply"] is True and pv["source_format"] == "text"


def test_image_only_pdf_reports_no_text_layer():
    pytest.importorskip("pypdf")
    pv = broker_1099b.preview_statement("etrade", pdf_bytes=make_pdf([[""]]), known_symbols=SYMBOLS)
    assert pv["can_apply"] is False
    assert any("text" in e["error"].lower() for e in pv["errors"])


def test_garbage_bytes_are_a_clean_error():
    pytest.importorskip("pypdf")
    pv = broker_1099b.preview_statement("etrade", pdf_bytes=b"not a pdf", known_symbols=SYMBOLS)
    assert pv["can_apply"] is False and pv["errors"]


def test_importing_the_package_does_not_import_pypdf():
    import subprocess, sys
    code = "import sys; import src.broker_1099b; sys.exit(1 if 'pypdf' in sys.modules else 0)"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0
