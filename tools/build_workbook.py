from pathlib import Path
import sys


def _configure_console_encoding():
    """Avoid Windows cp1252 UnicodeEncodeError when build logs contain Unicode."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


_configure_console_encoding()


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Thin CLI wrapper: the build steps live in src.build_entry.run_build so the same
# logic can run either here as a subprocess (desktop default) or in-process on a
# mobile worker thread. Retained at this path because the PyInstaller script
# runner, workbook/plan routes, and package docs invoke it directly.
if __name__ == "__main__":
    from src.build_entry import run_build

    result = run_build()
    raise SystemExit(result.returncode)
