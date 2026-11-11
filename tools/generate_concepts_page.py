"""Generate frontend/concepts.html, the in-app Concepts Guide, from the help registry (W3-10 / DOC-003).

The registry (frontend/js/help_registry.js: HELP_PAGES and GLOSSARY) stays the one source of truth;
this page is rebuilt from it, so it cannot drift from the nav. The packaged build ships ``frontend/``
but not ``documentation/``, which is why the guide lives here rather than as a Word file.

    python tools/generate_concepts_page.py          # rewrite frontend/concepts.html
    python tools/generate_concepts_page.py --check  # exit 1 if the committed page is stale
"""
from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "frontend" / "js" / "help_registry.js"
OUT = ROOT / "frontend" / "concepts.html"

_NODE = """
globalThis.window = globalThis;
const m = await import(process.argv[1]);
process.stdout.write(JSON.stringify({ pages: m.HELP_PAGES, glossary: m.GLOSSARY }));
"""

_FIELDS = (("whatFor", "What it is for"), ("connections", "What it connects to"),
           ("options", "Your options"), ("impact", "What it changes"))


def load_registry() -> dict:
    proc = subprocess.run(["node", "--input-type=module", "-e", _NODE, REGISTRY.resolve().as_uri()],
                          capture_output=True, text=True, encoding="utf-8", check=True, timeout=60)
    return json.loads(proc.stdout)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def render(reg: dict) -> str:
    e = html.escape
    pages = [(k, p) for k, p in reg["pages"].items() if p.get("title")]
    terms = sorted(reg["glossary"].items(), key=lambda kv: kv[0].lower())
    toc = "".join(f'<li><a href="#p-{e(_slug(k))}">{e(p["title"])}</a></li>' for k, p in pages)
    body = []
    for k, p in pages:
        rows = "".join(f"<h3>{label}</h3><p>{e(p[f])}</p>" for f, label in _FIELDS if p.get(f))
        used = "".join(f'<li><a href="#t-{e(_slug(t))}">{e(t)}</a></li>' for t in p.get("terms", []) if t in reg["glossary"])
        body.append(f'<section id="p-{e(_slug(k))}"><h2>{e(p["title"])}</h2><p class="lead">{e(p.get("summary", ""))}</p>'
                    f'{rows}{"<h3>Words used here</h3><ul>" + used + "</ul>" if used else ""}</section>')
    gloss = "".join(f'<dt id="t-{e(_slug(t))}">{e(t)}</dt><dd>{e(d)}</dd>' for t, d in terms)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Concepts Guide</title>
<style>
:root {{ --bg:#fff; --fg:#1b2430; --muted:#57606a; --line:#d0d7de; --accent:#0b5cad; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14181d; --fg:#e6edf3; --muted:#9aa4af; --line:#30363d; --accent:#6cb0ff; }} }}
body {{ background:var(--bg); color:var(--fg); font:16px/1.55 system-ui, sans-serif; margin:0; }}
main {{ max-width:820px; margin:0 auto; padding:16px; }}
a {{ color:var(--accent); }} h1 {{ font-size:1.6rem; }} h2 {{ margin-top:2.2rem; border-top:1px solid var(--line); padding-top:1rem; }}
h3 {{ font-size:1rem; margin:1rem 0 .2rem; }} .lead {{ color:var(--muted); }} dt {{ font-weight:600; margin-top:.8rem; }} dd {{ margin:0; }}
nav ul {{ columns:2; padding-left:1.1rem; }}
</style>
</head>
<body>
<main>
<h1>Concepts Guide</h1>
<p>Plain-English help for every page and the words used on them. It is built from the same help text the right-hand help panel shows.
Back to the <a href="index.html">planner</a>.</p>
<nav aria-label="Pages"><h2>Pages</h2><ul>{toc}<li><a href="#glossary">Glossary</a></li></ul></nav>
{"".join(body)}
<section id="glossary"><h2>Glossary</h2><dl>{gloss}</dl></section>
</main>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    text = render(load_registry())
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print("frontend/concepts.html is stale: run python tools/generate_concepts_page.py")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
