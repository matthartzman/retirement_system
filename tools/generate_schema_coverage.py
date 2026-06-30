from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.schema_registry import generate_schema_coverage
if __name__ == '__main__':
    print(generate_schema_coverage())
