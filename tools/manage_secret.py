from __future__ import annotations
from pathlib import Path
import argparse
import getpass
import hashlib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.secrets_store import set_secret, get_secret, encryption_status


def fingerprint(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Store or inspect encrypted/obfuscated API keys")
    ap.add_argument("name", help="secret name, e.g. fmp_api_key")
    ap.add_argument("--workspace", default="local")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.show:
        val = get_secret(args.name, args.workspace)
        print({"configured": bool(val), "fingerprint": fingerprint(val), **encryption_status()})
    else:
        val = getpass.getpass(f"Value for {args.name}: ")
        set_secret(args.name, val, args.workspace)
        print({"stored": True, "fingerprint": fingerprint(val), **encryption_status()})
