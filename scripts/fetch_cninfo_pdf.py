from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

UA = "Mozilla/5.0"
BASES = [
    "https://static.cninfo.com.cn/",
    "https://static.cninfo.com.cn/new/",
    "https://www.cninfo.com.cn/",
    "https://www.cninfo.com.cn/new/",
]


def try_fetch(url: str) -> bytes:
    req = Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.cninfo.com.cn/new/disclosure/stock",
        "Accept": "application/pdf,*/*",
    })
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("adjunctUrl")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    adjunct = args.adjunctUrl.lstrip('/')
    out = Path(args.out) if args.out else Path("../runs/pdf.bin")
    out.parent.mkdir(parents=True, exist_ok=True)

    last_error = None
    for base in BASES:
        url = base + adjunct
        try:
            data = try_fetch(url)
            out.write_bytes(data)
            print(json.dumps({"url": url, "saved": str(out), "bytes": len(data)}, ensure_ascii=False))
            return
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"

    raise SystemExit(last_error or "failed to fetch pdf")


if __name__ == '__main__':
    main()
