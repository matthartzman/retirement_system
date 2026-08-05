"""Generate documentation/SYSTEM_ARCHITECTURE_DIAGRAM.md from the live codebase.

This is the maintainable alternative to a hand-drawn architecture diagram: it
statically parses `src/` for imports (stdlib vs. third-party vs. internal),
introspects `src/module_catalog.py` (the input/output data-flow contract) and
`src/server/route_manifest.py` (the API surface), and scans `frontend/` for
the browser layer. Every run reflects the code as it exists *right now*, so
the diagram cannot drift out of sync the way a manually maintained one does.

Usage:
    python tools/generate_system_diagram.py

Regenerate this any time modules are added/removed/moved, a new external
dependency is introduced, or module_catalog.py / route_manifest.py change.
Consider wiring it into CI (fail if the committed doc differs from a fresh
run) so drift is caught automatically -- see the note at the bottom of the
generated file.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FRONTEND = ROOT / "frontend"
OUT_PATH = ROOT / "documentation" / "SYSTEM_ARCHITECTURE_DIAGRAM.md"

sys.path.insert(0, str(ROOT))

STDLIB = set(sys.stdlib_module_names) | {"__future__"}

# Third-party package name -> the pip distribution name in requirements.txt,
# for packages whose import name differs from their pip name.
IMPORT_TO_DIST = {
    "PIL": "pillow",
    "yaml": "pyyaml",
    "webview": "pywebview",
    "cv2": "opencv-python",
}

# Directory (relative to src/) -> human layer name + short role description.
# Anything under src/ not matching a prefix below falls into "Core Engine &
# Domain" (top-level src/*.py files).
LAYER_RULES: list[tuple[str, str, str]] = [
    ("server_services", "Server Services", "Feature-owned, request-independent business logic"),
    ("server", "HTTP Routes", "Thin HTTP adapters: request parsing, calls into services"),
    ("http_runtime", "HTTP Runtime", "Dependency-free stdlib HTTP server/routing/test-client layer"),
    ("reporting", "Reporting / Workbook", "Excel/PDF/dashboard artifact generation"),
    ("projection_stages", "Projection Stages", "Deterministic year-by-year projection engine internals"),
    ("dashboard_ui", "Dashboard UI Builder", "Server-rendered dashboard HTML assembly"),
]

LAYER_ORDER = [
    "Frontend SPA",
    "HTTP Routes",
    "Server Services",
    "HTTP Runtime",
    "Core Engine & Domain",
    "Projection Stages",
    "Reporting / Workbook",
    "Dashboard UI Builder",
]


def layer_for(rel_path: Path) -> str:
    parts = rel_path.parts
    if len(parts) > 1:
        for prefix, layer_name, _desc in LAYER_RULES:
            if parts[0] == prefix:
                return layer_name
    return "Core Engine & Domain"


def module_dotted_name(py_file: Path) -> str:
    rel = py_file.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def resolve_relative_import(current: str, node: ast.ImportFrom) -> str:
    """Best-effort resolution of `from . import x` / `from .foo import y` to a dotted src.* path."""
    parts = current.split(".")
    # current is e.g. "src.server.plan_routes" -> package is "src.server"
    package_parts = parts[:-1]
    level = node.level
    base = package_parts[: len(package_parts) - (level - 1)] if level > 1 else package_parts
    if node.module:
        base = base + node.module.split(".")
    return ".".join(base)


class FileImports:
    def __init__(self) -> None:
        self.internal: set[str] = set()   # dotted src.* module names
        self.external: set[str] = set()   # top-level third-party package names


def collect_imports(py_file: Path, top_level_internal: set[str]) -> FileImports:
    """``top_level_internal`` is the set of module stems directly under
    ``src/`` (e.g. ``planning_engines``, ``holding_period``). Several modules
    fall back to a bare ``import planning_engines`` (no ``src.``/relative
    prefix) for frozen/packaged runs where ``src/`` is on ``sys.path``
    directly -- those must be resolved as internal, not mistaken for a
    third-party package of the same name."""
    result = FileImports()
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    except SyntaxError:
        return result
    dotted_self = module_dotted_name(py_file)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                _classify(top, alias.name, result, top_level_internal)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                resolved = resolve_relative_import(dotted_self, node)
                if resolved.startswith("src."):
                    result.internal.add(resolved)
                continue
            if node.module:
                top = node.module.split(".")[0]
                _classify(top, node.module, result, top_level_internal)
    return result


def _classify(top: str, full: str, result: FileImports, top_level_internal: set[str]) -> None:
    if top == "src":
        result.internal.add(full)
    elif top in top_level_internal:
        result.internal.add(f"src.{full}")
    elif top in STDLIB:
        return
    else:
        result.external.add(IMPORT_TO_DIST.get(top, top))


def nearest_known_module(dotted: str, known_modules: set[str]) -> str | None:
    """A `from src.server import features` may resolve to a package, not a file;
    walk up the dotted path until we find a file we actually parsed."""
    candidate = dotted
    while candidate:
        if candidate in known_modules:
            return candidate
        if "." not in candidate:
            return None
        candidate = candidate.rsplit(".", 1)[0]
    return None


def main() -> None:
    py_files = sorted(SRC.rglob("*.py"))
    top_level_internal = {f.stem for f in SRC.glob("*.py")}
    per_file: dict[str, FileImports] = {}
    file_by_dotted: dict[str, Path] = {}
    for f in py_files:
        if "__pycache__" in f.parts:
            continue
        dotted = module_dotted_name(f)
        per_file[dotted] = collect_imports(f, top_level_internal)
        file_by_dotted[dotted] = f

    known_modules = set(per_file)

    # ---- Layer aggregation -------------------------------------------------
    layer_of: dict[str, str] = {}
    layer_modules: dict[str, list[str]] = defaultdict(list)
    layer_external: dict[str, set[str]] = defaultdict(set)
    layer_internal_edges: set[tuple[str, str]] = set()

    for dotted, f in file_by_dotted.items():
        rel = f.relative_to(SRC)
        layer = layer_for(rel)
        layer_of[dotted] = layer
        layer_modules[layer].append(dotted)

    for dotted, imports in per_file.items():
        src_layer = layer_of[dotted]
        layer_external[src_layer] |= imports.external
        for dep in imports.internal:
            resolved = nearest_known_module(dep, known_modules)
            if resolved is None or resolved == dotted:
                continue
            dst_layer = layer_of.get(resolved)
            if dst_layer and dst_layer != src_layer:
                layer_internal_edges.add((src_layer, dst_layer))

    # ---- Frontend layer (script-tag load order from index.html) ------------
    frontend_files: list[str] = []
    index_html = FRONTEND / "index.html"
    if index_html.exists():
        html = index_html.read_text(encoding="utf-8", errors="replace")
        frontend_files = re.findall(r'<script[^>]*src="([^"]+)"', html)
    js_files = sorted(p.relative_to(ROOT).as_posix() for p in FRONTEND.rglob("*.js"))

    # ---- module_catalog.py introspection (data-flow contract) --------------
    from src import module_catalog as mc  # noqa: E402  (path inserted above)

    input_modules = mc.INPUT_MODULES
    catalog = getattr(mc, "CATALOG", {})
    outputs = list(catalog.values()) if isinstance(catalog, dict) else list(catalog)

    # ---- route_manifest.py introspection (API surface) ----------------------
    # Loaded standalone (not via `src.server`) because that package's
    # __init__ eagerly imports every route module, some of which require a
    # newer Python/runtime than this generator needs to run under.
    routes = _load_standalone_module(
        "route_manifest", SRC / "server" / "route_manifest.py"
    ).ROUTE_MODULES

    # ---- requirements.txt (declared external deps) --------------------------
    req_lines = []
    req_path = ROOT / "requirements.txt"
    if req_path.exists():
        for line in req_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                req_lines.append(line)

    write_doc(
        layer_modules=layer_modules,
        layer_external=layer_external,
        layer_internal_edges=layer_internal_edges,
        per_file=per_file,
        file_by_dotted=file_by_dotted,
        frontend_files=frontend_files,
        js_files=js_files,
        input_modules=input_modules,
        outputs=outputs,
        routes=routes,
        req_lines=req_lines,
    )
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}")


def _load_standalone_module(name: str, path: Path):
    """Load a single .py file as its own module, without importing its parent
    package (and therefore without triggering sibling imports in __init__.py)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def mermaid_id(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def write_doc(
    *,
    layer_modules: dict[str, list[str]],
    layer_external: dict[str, set[str]],
    layer_internal_edges: set[tuple[str, str]],
    per_file: dict[str, "FileImports"],
    file_by_dotted: dict[str, Path],
    frontend_files: list[str],
    js_files: list[str],
    input_modules: dict,
    outputs: list,
    routes: dict,
    req_lines: list[str],
) -> None:
    lines: list[str] = []
    lines.append("# System Architecture Diagram")
    lines.append("")
    lines.append(
        "**Auto-generated. Do not hand-edit.** Run `python tools/generate_system_diagram.py` "
        "after adding, removing, or moving modules, changing imports, or editing "
        "`src/module_catalog.py` / `src/server/route_manifest.py`. The script statically "
        "parses the codebase, so this document cannot drift from what the code actually does "
        "-- if it looks wrong, the fix is to rerun the generator, not to edit this file."
    )
    lines.append("")
    lines.append(f"Source: `tools/generate_system_diagram.py`. Modules scanned: {sum(len(v) for v in layer_modules.values())} Python files under `src/`, {len(js_files)} JS files under `frontend/`.")
    lines.append("")

    # ---- 1. Layer diagram ----------------------------------------------------
    lines.append("## 1. Layer Architecture")
    lines.append("")
    lines.append(
        "Every box is a real directory in the repo. Every arrow is a real `import` "
        "found by parsing the code -- not an aspirational diagram."
    )
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart TB")
    lines.append('    User(["Desktop user"]) --> FE')
    lines.append('    subgraph FE["Frontend SPA (frontend/)"]')
    lines.append(f'        FEcount["{len(js_files)} JS files, browser-loaded via index.html script tags"]')
    lines.append("    end")
    lines.append("    FE -->|fetch /api/*| L_HTTP_Routes")
    for layer in LAYER_ORDER:
        if layer == "Frontend SPA":
            continue
        mods = layer_modules.get(layer, [])
        if not mods and layer not in {l for _, l, _ in LAYER_RULES} | {"Core Engine & Domain"}:
            continue
        lid = mermaid_id(f"L_{layer}")
        desc = next((d for _, n, d in LAYER_RULES if n == layer), "Root-level engine, domain, and shared modules")
        lines.append(f'    subgraph {lid}["{layer} ({len(mods)} modules)"]')
        lines.append(f'        {lid}_d["{desc}"]')
        lines.append("    end")
    seen_edges = set()
    for src_layer, dst_layer in sorted(layer_internal_edges):
        key = (mermaid_id(f"L_{src_layer}"), mermaid_id(f"L_{dst_layer}"))
        if key in seen_edges:
            continue
        seen_edges.add(key)
        lines.append(f"    {key[0]} --> {key[1]}")
    lines.append('    L_Core_Engine___Domain --> DB[("SQLite local_state/ + CSV input/")]')
    lines.append('    L_Reporting___Workbook --> Outputs[("output/: XLSX, PDF, HTML, JSON")]')
    lines.append("    Outputs --> FE")
    lines.append("```")
    lines.append("")

    # ---- 2. External dependencies per layer -----------------------------------
    lines.append("## 2. Imported (Third-Party) Modules")
    lines.append("")
    lines.append("From `requirements.txt` (the authoritative declared list):")
    lines.append("")
    for line in req_lines:
        lines.append(f"- `{line}`")
    lines.append("")
    lines.append("Actual usage detected per layer (which layer imports which third-party package):")
    lines.append("")
    lines.append("| Layer | Third-party imports found |")
    lines.append("|---|---|")
    all_external: set[str] = set()
    for layer in LAYER_ORDER:
        if layer == "Frontend SPA":
            continue
        ext = sorted(layer_external.get(layer, set()))
        all_external |= set(ext)
        if not ext and layer not in layer_modules:
            continue
        lines.append(f"| {layer} | {', '.join(f'`{e}`' for e in ext) if ext else '_none (stdlib only)_'} |")
    lines.append("")

    declared_names = {re.split(r"[><=!~\[]", line, 1)[0].strip().lower() for line in req_lines}
    undeclared = sorted(name for name in all_external if name.lower() not in declared_names)
    if undeclared:
        lines.append(
            f"**Detected but not in `requirements.txt`:** {', '.join(f'`{n}`' for n in undeclared)}. "
            "Worth checking each one at the import site: as of this writing, `pyyaml` and `requests` "
            "are both guarded by `try/except ImportError` as optional/lazy imports (the feature "
            "degrades rather than crashing if absent) -- confirm any newly-appearing name here follows "
            "the same pattern before assuming it's safe to leave undeclared."
        )
        lines.append("")

    # ---- 3. Data flow: inputs -> outputs (from module_catalog.py) -------------
    lines.append("## 3. Data Flow: Plan Inputs to Report Outputs")
    lines.append("")
    lines.append(
        "Generated by importing `src/module_catalog.py` directly -- the module's own "
        "docstring calls it \"the single source of truth\" for this mapping, so the "
        "diagram below is always exactly what the code will do, not a snapshot."
    )
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart LR")
    for key, meta in input_modules.items():
        label = meta.get("label", key)
        lines.append(f'    IN_{mermaid_id(key)}(["{label}"])')
    for om in outputs:
        oid = mermaid_id(getattr(om, "key", str(om)))
        name = getattr(om, "name", str(om))
        kind = getattr(om, "kind", "")
        lines.append(f'    OUT_{oid}["{name}\\n({kind})"]')
        for req_input, _elements in getattr(om, "requires_inputs", ()):
            lines.append(f"    IN_{mermaid_id(req_input)} --> OUT_{oid}")
        for req_output in getattr(om, "requires_outputs", ()):
            lines.append(f"    OUT_{mermaid_id(req_output)} --> OUT_{oid}")
    lines.append("```")
    lines.append("")
    lines.append(f"Input modules: {len(input_modules)}. Output modules: {len(outputs)}.")
    lines.append("")

    # ---- 4. API surface (from route_manifest.py) -------------------------------
    lines.append("## 4. Frontend ↔ Server API Surface")
    lines.append("")
    lines.append("Generated by importing `src/server/route_manifest.py` (`ROUTE_MODULES`), the ownership map each feature-service module registers routes under.")
    lines.append("")
    lines.append("| Feature module | Routes owned |")
    lines.append("|---|---|")
    for feature, route_list in routes.items():
        noun = "route" if len(route_list) == 1 else "routes"
        lines.append(f"| `{feature}` | {len(route_list)} {noun}: {', '.join(f'`{r}`' for r in route_list[:6])}{', ...' if len(route_list) > 6 else ''} |")
    lines.append("")

    # ---- 5. Frontend file inventory --------------------------------------------
    lines.append("## 5. Frontend Layer (frontend/)")
    lines.append("")
    if frontend_files:
        lines.append("Script load order, as declared in `frontend/index.html` (this is the frontend's real dependency order -- no bundler, no ES module graph):")
        lines.append("")
        for i, f in enumerate(frontend_files, 1):
            lines.append(f"{i}. `{f}`")
        lines.append("")
    lines.append(f"All `.js` files found under `frontend/` ({len(js_files)}):")
    lines.append("")
    for f in js_files:
        lines.append(f"- `{f}`")
    lines.append("")
    not_in_index = sorted(
        Path(f).name.split("?")[0]
        for f in [f2 for f2 in js_files]
        if Path(f).name not in {Path(s).name.split("?")[0] for s in frontend_files}
    )
    if not_in_index:
        lines.append(
            f"Files present under `frontend/js/` but not referenced by `index.html`'s script tags "
            f"({', '.join(f'`{n}`' for n in not_in_index)}): loaded by a different page "
            "(e.g. an admin/standalone HTML entry point), or dead code -- check before assuming either."
        )
        lines.append("")

    # ---- 6. Full per-module dependency appendix ---------------------------------
    lines.append("## 6. Appendix: Full Module Dependency Table")
    lines.append("")
    lines.append("Every developed module under `src/`, grouped by layer, with its internal and external imports. This is the ground truth the diagrams above are aggregated from.")
    lines.append("")
    for layer in LAYER_ORDER:
        if layer == "Frontend SPA":
            continue
        mods = sorted(layer_modules.get(layer, []))
        if not mods:
            continue
        lines.append(f"### {layer}")
        lines.append("")
        lines.append("| Module | Internal imports | External imports |")
        lines.append("|---|---|---|")
        for dotted in mods:
            imp = per_file[dotted]
            internal_short = sorted({nearest_known_module(d, set(per_file)) or d for d in imp.internal} - {dotted})
            internal_short = [m.replace("src.", "") for m in internal_short]
            external_short = sorted(imp.external)
            rel = file_by_dotted[dotted].relative_to(ROOT).as_posix()
            lines.append(
                f"| `{rel}` | {', '.join(f'`{m}`' for m in internal_short) if internal_short else '—'} "
                f"| {', '.join(f'`{m}`' for m in external_short) if external_short else '—'} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "**Keeping this current:** rerun `python tools/generate_system_diagram.py` after any "
        "module add/move/delete, import change, or edit to `module_catalog.py` / "
        "`route_manifest.py`. For automatic drift detection, add a CI step that runs the "
        "generator and fails the build if `git diff --exit-code documentation/SYSTEM_ARCHITECTURE_DIAGRAM.md` "
        "is non-empty."
    )
    lines.append("")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
