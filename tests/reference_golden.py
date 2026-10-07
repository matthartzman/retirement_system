"""Golden fixtures for reference.db getters (WP3.1).

A golden file ``tests/fixtures/reference_golden/<name>.json`` is the canonical
encoding of what the OLD file loader returned, recorded by
``tools/capture_reference_golden.py`` before that loader is deleted. The new
getter registered under the same name in
``src.stores.ref_getters.GOLDEN_GETTERS`` must encode to the identical text.

The encoding is JSON that keeps every distinction plain JSON loses: ``1`` vs
``1.0`` (floats keep their ``repr``), ``bool`` vs ``int``, tuples vs lists, dict
key order and non-string keys, sets, dataclasses, namedtuples, dates, Decimal and
numpy values. Unknown types raise ``TypeError`` (extend ``to_canonical`` rather
than coercing). Comparison is on the text, so it is exact.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "reference_golden"


def to_canonical(v: Any) -> Any:
    """A JSON-ready tree that encodes ``v`` without losing type distinctions."""
    t = type(v)
    if v is None or t in (bool, int, float, str):
        return v
    if t is list:
        return [to_canonical(x) for x in v]
    if t is tuple:
        return {"$tuple": [to_canonical(x) for x in v]}
    if isinstance(v, tuple) and hasattr(v, "_fields"):
        return {"$namedtuple": f"{t.__module__}.{t.__qualname__}",
                "fields": {f: to_canonical(getattr(v, f)) for f in v._fields}}
    if t is dict:
        if all(type(k) is str and not k.startswith("$") for k in v):
            return {k: to_canonical(x) for k, x in v.items()}
        return {"$dict": [[to_canonical(k), to_canonical(x)] for k, x in v.items()]}
    if t in (set, frozenset):
        items = sorted((to_canonical(x) for x in v), key=lambda c: json.dumps(c, sort_keys=True))
        return {f"${t.__name__}": items}
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {"$dataclass": f"{t.__module__}.{t.__qualname__}",
                "fields": {f.name: to_canonical(getattr(v, f.name)) for f in dataclasses.fields(v)}}
    if t is _dt.date:
        return {"$date": v.isoformat()}
    if t is _dt.datetime:
        return {"$datetime": v.isoformat()}
    if t is decimal.Decimal:
        return {"$decimal": str(v)}
    if t.__module__ == "numpy":
        if t.__name__ == "ndarray":
            return {"$ndarray": str(v.dtype), "shape": list(v.shape), "data": to_canonical(v.tolist())}
        if hasattr(v, "item") and hasattr(v, "dtype"):
            return {"$numpy": str(v.dtype), "value": to_canonical(v.item())}
    raise TypeError(f"no canonical encoding for {t.__module__}.{t.__qualname__}; extend tests/reference_golden.py")


def dumps(value: Any) -> str:
    """Canonical golden text (stable, diff-friendly, newline-terminated)."""
    return json.dumps(to_canonical(value), indent=1, ensure_ascii=False, allow_nan=True) + "\n"


def golden_path(name: str) -> Path:
    return GOLDEN_DIR / f"{name}.json"


def golden_names() -> list[str]:
    return sorted(p.stem for p in GOLDEN_DIR.glob("*.json"))


def write_golden(name: str, value: Any, *, force: bool = False) -> Path:
    """Record ``value`` (the OLD loader's output) as golden ``name``."""
    path = golden_path(name)
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; goldens are captured once from the old loader (use --force)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(value), encoding="utf-8", newline="\n")
    return path


DIGEST_KEY = "$sha256_of_canonical_text"


def digest_golden(text: str) -> str:
    """Compact golden for a huge value (the national ZIP table): the SHA-256 of the
    exact canonical text that ``write_golden`` would have written, plus its size."""
    return json.dumps({DIGEST_KEY: hashlib.sha256(text.encode("utf-8")).hexdigest(), "chars": len(text)}, indent=1) + "\n"


def assert_getter_matches_golden(name: str, value: Any, *, context: int = 3, max_lines: int = 60) -> None:
    """Fail with a unified diff if ``value`` does not encode exactly to golden ``name``."""
    path = golden_path(name)
    assert path.is_file(), f"no golden fixture {path.relative_to(ROOT)}; capture it from the old loader first"
    expected = path.read_text(encoding="utf-8")
    actual = dumps(value)
    if expected.lstrip().startswith("{") and DIGEST_KEY in expected[:80]:
        assert digest_golden(actual) == expected, f"getter {name!r} differs from its digest golden (sha256 of canonical text)"
        return
    if actual != expected:
        diff = list(difflib.unified_diff(expected.splitlines(), actual.splitlines(),
                                         f"golden/{name}.json", f"getter {name}", n=context, lineterm=""))
        more = f"\n... {len(diff) - max_lines} more diff lines" if len(diff) > max_lines else ""
        raise AssertionError(f"getter {name!r} differs from its golden fixture:\n" + "\n".join(diff[:max_lines]) + more)
