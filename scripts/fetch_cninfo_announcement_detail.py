from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Placeholder for CNINFO announcement detail fetch")
    ap.add_argument("announcementId")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    result = {
        "announcementId": args.announcementId,
        "status": "todo",
        "message": "detail API not wired yet; current reliable path remains announcement list -> PDF/text extraction",
    }
    out = Path(args.out) if args.out else Path(f"../runs/{args.announcementId}_detail.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
