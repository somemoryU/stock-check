from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

UA = "Mozilla/5.0"
BASE = "https://www.cninfo.com.cn/new/hisAnnouncement/query"


def fetch_json(url: str, data: bytes) -> dict:
    req = Request(url, data=data, headers={
        "User-Agent": UA,
        "Referer": "https://www.cninfo.com.cn/new/disclosure/stock",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    })
    with urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    return json.loads(raw)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch CNINFO announcement list")
    ap.add_argument("stock", help="stock code, e.g. 000993")
    ap.add_argument("orgId", help="orgId from stock page")
    ap.add_argument("--pageSize", type=int, default=20)
    ap.add_argument("--pageNum", type=int, default=1)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--tabName", default="fulltext")
    ap.add_argument("--column", default="szse")
    ap.add_argument("--category", default="")
    ap.add_argument("--plate", default="szse")
    ap.add_argument("--searchkey", default="")
    ap.add_argument("--sortName", default="")
    ap.add_argument("--sortType", default="")
    ap.add_argument("--outdir", default="", help="output dir")
    args = ap.parse_args()

    outdir = Path(args.outdir) if args.outdir else Path(f"../runs/{args.stock}/raw")
    outdir.mkdir(parents=True, exist_ok=True)
    for pn in range(args.pageNum, args.pageNum + args.pages):
        payload = {
            "stock": f"{args.stock},{args.orgId}",
            "tabName": args.tabName,
            "pageSize": args.pageSize,
            "pageNum": pn,
            "column": args.column,
            "category": args.category,
            "plate": args.plate,
            "seDate": "",
            "searchkey": args.searchkey,
            "secid": "",
            "sortName": args.sortName,
            "sortType": args.sortType,
            "isHLtitle": "true",
        }
        data = urlencode(payload).encode("utf-8")
        result = fetch_json(BASE, data)
        anns = result.get("announcements") or []
        result["announcements"] = anns
        out = outdir / f"announcements_p{pn}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "saved": str(out),
            "totalAnnouncement": result.get("totalAnnouncement"),
            "count": len(anns),
            "pageNum": pn,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
