"""Regression: tools/set_local_mode.py must never truncate system_config.csv."""
import csv
import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("set_local_mode", ROOT / "tools" / "set_local_mode.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rows(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def test_reset_keeps_every_row_of_the_real_config(tmp_path):
    cfg = tmp_path / "system_config.csv"
    shutil.copy(ROOT / "system_config.csv", cfg)
    before = _rows(cfg)
    assert _load().main(cfg) == 0
    after = _rows(cfg)
    assert len(after) >= len(before)
    assert {r[2] for r in before if len(r) > 2} <= {r[2] for r in after if len(r) > 2}


def test_malformed_row_with_extra_fields_does_not_truncate_file(tmp_path):
    cfg = tmp_path / "system_config.csv"
    cfg.write_text(
        "section,subsection,label,value,units,notes\n"
        "Market Pricing,Holdings,pricing_mode,LIVE,choice,CACHE = a, b; LIVE = c, d\n"
        "Rebalancing,Optimization,max_tax_cost_bps,25,bps,keep me\n",
        encoding="utf-8",
    )
    assert _load().main(cfg) == 0
    labels = [r[2] for r in _rows(cfg) if len(r) > 2]
    assert "pricing_mode" in labels and "max_tax_cost_bps" in labels
    assert not list(tmp_path.glob("*.tmp"))
