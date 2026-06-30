"""Build a clean distributable zip package.

This package builder intentionally excludes local Plan Data and runtime state.
In particular, the release artifact must never include the input/ folder; users
load/select Plan Data at runtime through the UI.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT.parent / f"{ROOT.name}.zip"
EXCLUDED_DIR_NAMES = {
    ".claude",
    "input",
    "data",
    "sample_plan_data",
    "output",
    "saved_plans",
    "logs",
    "local_state",
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".venv",
    "venv",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
ADVISOR_SAFE_FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log"}
EXCLUDED_RELATIVE_PATHS = {
    Path("wsgi.py"),
    Path("output") / "market_price_cache.json",
    Path("output") / "live_pricing_test_results.json",
    Path("output") / ("retirement_dashboard_" + "ui.html"),
}


def _skip_rel(rel: Path) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in rel.parts):
        return True
    if rel.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if rel.suffix.lower() in ADVISOR_SAFE_FORBIDDEN_SUFFIXES:
        return True
    if rel in EXCLUDED_RELATIVE_PATHS:
        return True
    if any(part.lower() in {"secrets.db", "audit_log.jsonl", "market_price_cache.json"} for part in rel.parts):
        return True
    return False


def _skip_source(path: Path) -> bool:
    return _skip_rel(path.relative_to(ROOT))


def _copy_clean_tree(stage: Path) -> None:
    for src in ROOT.rglob("*"):
        rel = src.relative_to(ROOT)
        if _skip_rel(rel):
            continue
        dst = stage / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _compile_python_sources(stage: Path) -> None:
    for base in [stage / "src", stage / "tools", stage / "tests"]:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")


def _run_prepackage_checks(stage: Path) -> None:
    # Compile Python in memory so syntax/import-name mistakes are caught without
    # leaving __pycache__ files in the staged package.
    _compile_python_sources(stage)

    # Static guard for the feature-owned build job registry. It catches the class
    # of issue where the route references build progress helpers without the
    # extracted service contract being packaged.
    route = stage / "src" / "server" / "workbook_routes.py"
    route_text = route.read_text(encoding="utf-8")
    service = stage / "src" / "server_services" / "build_job_service.py"
    service_text = service.read_text(encoding="utf-8") if service.exists() else ""
    report_service = stage / "src" / "server_services" / "report_service.py"
    report_service_text = report_service.read_text(encoding="utf-8") if report_service.exists() else ""
    spending_service = stage / "src" / "server_services" / "spending_service.py"
    spending_service_text = spending_service.read_text(encoding="utf-8") if spending_service.exists() else ""
    strategy_asset_service = stage / "src" / "server_services" / "strategy_asset_service.py"
    strategy_asset_service_text = strategy_asset_service.read_text(encoding="utf-8") if strategy_asset_service.exists() else ""
    portfolio_service = stage / "src" / "server_services" / "portfolio_service.py"
    portfolio_service_text = portfolio_service.read_text(encoding="utf-8") if portfolio_service.exists() else ""
    secret_service = stage / "src" / "server_services" / "secret_service.py"
    secret_service_text = secret_service.read_text(encoding="utf-8") if secret_service.exists() else ""
    required_tokens = [
        ("workbook route", "build_job_service"),
        ("workbook route", "_BUILD_JOBS = build_job_service.BuildJobRegistry()"),
        ("build job service", "class BuildJobRegistry"),
        ("build job service", "threading.RLock()"),
        ("build job service", "subprocess.Popen"),
        ("build job service", '[sys.executable, "-u", str(build_script)]'),
        ("report service", "def detailed_results_payload"),
        ("report service", "def local_output_file_payload"),
        ("spending service", "class SpendingService"),
        ("spending service", "def load_actuals_payload"),
        ("spending service", "def save_unified_budget_payload"),
        ("strategy asset service", "class StrategyAssetService"),
        ("strategy asset service", "def withdrawal_order_payload"),
        ("strategy asset service", "def add_insurance_policy_payload"),
        ("portfolio service", "def drift_payload"),
        ("secret service", "def set_secret_payload"),
    ]
    missing = []
    for owner, token in required_tokens:
        if owner == "workbook route":
            text = route_text
        elif owner == "report service":
            text = report_service_text
        elif owner == "spending service":
            text = spending_service_text
        elif owner == "strategy asset service":
            text = strategy_asset_service_text
        elif owner == "portfolio service":
            text = portfolio_service_text
        elif owner == "secret service":
            text = secret_service_text
        else:
            text = service_text
        if token not in text:
            missing.append(f"{owner}: {token}")
    if missing:
        raise SystemExit("Missing build-job service definitions: " + ", ".join(missing))

    if not (stage / "src" / "server" / "wsgi.py").exists():
        raise SystemExit("Missing canonical WSGI entry point: src/server/wsgi.py")

    # Run the package-clean check in-process against the staged root. This
    # avoids nested subprocess behavior in constrained CI/sandbox runners while
    # preserving the same check logic used by the standalone tool.
    import importlib.util as _importlib_util
    clean_path = ROOT / "tools" / "check_package_clean.py"
    spec = _importlib_util.spec_from_file_location("_retirement_check_package_clean", clean_path)
    if spec is None or spec.loader is None:
        raise SystemExit("Could not load package clean checker")
    mod = _importlib_util.module_from_spec(spec)
    old_root = getattr(mod, "ROOT", None)
    old_db = getattr(mod, "DB_PATH", None)
    spec.loader.exec_module(mod)
    mod.ROOT = stage
    mod.DB_PATH = stage / 'local_state' / 'retirement_system_v10.db'
    rc = int(mod.main() or 0)
    if old_root is not None:
        mod.ROOT = old_root
    if old_db is not None:
        mod.DB_PATH = old_db
    if rc:
        raise SystemExit(rc)


def _zip_tree(stage: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(stage.rglob("*")):
            rel = path.relative_to(stage)
            if path.is_dir() or _skip_rel(rel):
                continue
            zf.write(path, rel.as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="Build clean release package zip without local input/ Plan Data.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output zip path.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="retirement_package_") as tmp:
        stage = Path(tmp) / ROOT.name
        _copy_clean_tree(stage)
        _run_prepackage_checks(stage)
        _zip_tree(stage, args.output)
    print(f"Built clean package: {args.output}")
    print("Verified: input/ Plan Data folder is excluded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
