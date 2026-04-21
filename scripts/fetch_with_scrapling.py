from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRAPLING_PYTHON = "/Users/mix/scrapling/.venv/bin/python"

SCRIPT = r'''
import json
import sys
from scrapling.fetchers import Fetcher

url = sys.argv[1]
out = sys.argv[2]
fetcher = Fetcher(auto_match=False)
page = fetcher.get(url)
html = page.html_content
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)
print(json.dumps({
    "url": url,
    "saved": out,
    "bytes": len(html.encode('utf-8')),
    "status": getattr(page, 'status', None),
}, ensure_ascii=False))
'''


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch page HTML using scrapling as fallback")
    ap.add_argument("url")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not Path(SCRAPLING_PYTHON).exists():
        raise SystemExit(f"scrapling python not found: {SCRAPLING_PYTHON}")

    proc = subprocess.run(
        [SCRAPLING_PYTHON, "-c", SCRIPT, args.url, str(out)],
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
