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

from src.local_plan_data_sync import PLAN_DATA_FILES, sync_plan_data_from_env
from src.config_backend import materialize_workspace_files
from src.reporting.workbook_builder import main


def _materialize_server_working_copy():
    """Restore saved Plan Data files from the local SQLite mirror when needed.

    UI builds save the current on-screen/server working copy before launching
    this script. In database-backed mode some files may live in SQLite
    client_files rather than input/ after a package update or process restart.
    Materializing without overwriting preserves freshly saved CSVs while making
    split-file/holdings data available to the projection engine.
    """
    try:
        materialize_workspace_files(file_names=PLAN_DATA_FILES, overwrite_existing=False)
    except Exception as exc:
        print(f"WARN: Could not materialize saved Plan Data files from local store: {exc}")


if __name__ == "__main__":
    synced = sync_plan_data_from_env(ROOT)
    if synced:
        print(f"Loaded local Plan Data from {synced['source_dir']} before build")
    _materialize_server_working_copy()
    main()
