# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Retirement Plan System v10
# Build with:  pyinstaller retirement_planner.spec
# Output:      dist/retirement_planner/retirement_planner.exe  (onedir)
#
# The onedir layout is intentional: it keeps the _internal/ folder alongside
# writable user data (input/, output/, local_state/) and avoids the slow
# extraction step of --onefile on every launch.

import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files, copy_metadata

# ---------------------------------------------------------------------------
# Collect everything from the complex third-party packages so their
# data files, hook-resolved binaries, and lazy imports are included.
# ---------------------------------------------------------------------------
datas_collected    = []
binaries_collected = []
hiddenimports_collected = []

for pkg in ("numpy", "matplotlib", "reportlab", "openpyxl",
            "PIL", "cryptography"):
    _d, _b, _h = collect_all(pkg)
    datas_collected    += _d
    binaries_collected += _b
    hiddenimports_collected += _h

# copy_metadata ensures importlib.metadata.version() works inside the frozen
# exe for packages that query their own version at startup.
for _meta_pkg in ("numpy", "matplotlib", "reportlab",
                  "openpyxl", "Pillow", "cryptography", "pywebview"):
    try:
        datas_collected += copy_metadata(_meta_pkg)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Application source tree and static assets
# ---------------------------------------------------------------------------
# fmt: off
app_datas = [
    # Frontend (HTML, JS, CSS served by the stdlib local HTTP runtime)
    ("frontend",        "frontend"),
    # Read-only reference tables used at runtime
    ("reference_data",  "reference_data"),
    # Template input folder — seeded on first run, user edits in place
    ("input",           "input"),
    # Tool scripts called via subprocess.Popen([sys.executable, script, ...])
    # main.py's script-runner mode executes these inside the frozen interpreter
    ("tools",           "tools"),
    # src package source — ensures all modules are present even if PyInstaller's
    # static analysis misses them (e.g. modules not reachable from main.py)
    ("src",             "src"),
]
# fmt: on

all_datas = datas_collected + app_datas

# ---------------------------------------------------------------------------
# Hidden imports not caught by static analysis
# ---------------------------------------------------------------------------
hidden_imports = hiddenimports_collected + [
    # Local HTTP runtime is stdlib-only; no Flask/Werkzeug hidden imports.
    # numpy sub-packages accessed lazily (numpy itself is fully collected via collect_all)
    "numpy.core._multiarray_umath",
    "numpy.lib.npyio",
    # matplotlib backends — include Agg (non-interactive, used for server-side charting)
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_svg",
    # reportlab fonts and graphics
    "reportlab.graphics.charts",
    "reportlab.graphics.widgets",
    "reportlab.lib.pagesizes",
    "reportlab.lib.styles",
    "reportlab.platypus",
    # openpyxl lazy chart/drawing imports
    "openpyxl.chart",
    "openpyxl.drawing",
    "openpyxl.styles",
    "openpyxl.utils",
    # cryptography hazmat primitives
    "cryptography.hazmat.backends",
    "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.kdf",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    # PIL plugins (JPEG/PNG typically used by reportlab)
    "PIL.JpegImagePlugin",
    "PIL.PngImagePlugin",
    "PIL.BmpImagePlugin",
    "PIL.GifImagePlugin",
    # stdlib modules sometimes missed on Windows
    "sqlite3",
    "csv",
    "json",
    "zipfile",
    "xml.etree.ElementTree",
    # src package — collected below via collect_submodules but listed for safety
    "src",
    "src.server",
    "src.server.app_core",
    "src.server.base_routes",
    "src.server.workbook_routes",
    "src.server.admin_routes",
    "src.reporting",
    "src.reporting.workbook_builder",
    "src.reporting.enterprise_pdf",
    "src.reporting.dashboard",
]

# Collect every sub-module of the src package
hidden_imports += collect_submodules("src")

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ["main.py"],
    pathex=["."],          # project root on sys.path so "src" is importable
    binaries=binaries_collected,
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Test infrastructure — not needed at runtime
        "pytest", "_pytest", "py",
        # IPython / Jupyter not used here
        "IPython", "ipykernel", "notebook",
        # tkinter backend for matplotlib (not needed; we use Agg)
        "tkinter", "matplotlib.backends.backend_tkagg",
        "matplotlib.backends.backend_tk",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # onedir: binaries go in COLLECT, not embedded
    name="retirement_planner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,               # keep console visible so server logs are readable
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="frontend/assets/retirement_planner.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="retirement_planner",  # dist/retirement_planner/
)
