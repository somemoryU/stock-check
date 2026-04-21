from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
RUNS = ROOT / "runs"
PDFTOTEXT = "/opt/homebrew/bin/pdftotext"
PYTHON = sys.executable


def run_py(script: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = [PYTHON, str(SCRIPTS / script), *args]
    return subprocess.run(cmd, cwd=str(SCRIPTS), capture_output=True, text=True, check=check)


def extract_meta_from_f10(html: str) -> dict[str, str]:
    patterns = {
        "stockCode": r'stockCode\s*=\s*"([^"]+)"',
        "orgId": r'orgId\s*=\s*"([^"]+)"',
        "plate": r'plate\s*=\s*"([^"]+)"',
    }
    out: dict[str, str] = {}
    for key, pattern in patterns.items():
        m = re.search(pattern, html)
        if m:
            out[key] = m.group(1)
    return out


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def first_announcement_match(pages: list[Path], keywords: list[str]) -> dict[str, Any] | None:
    normalized = [k.lower() for k in keywords]
    for page in pages:
        data = load_json(page)
        for item in data.get("announcements", []):
            title = str(item.get("announcementTitle", ""))
            low = title.lower()
            if all(k in low for k in normalized):
                return item
    return None


def choose_report_targets(pages: list[Path]) -> dict[str, dict[str, Any]]:
    targets = {
        "annual_report": ["年度报告"],
        "semiannual_report": ["半年度报告"],
        "q3_report": ["三季度报告"],
        "earnings_forecast": ["业绩预告"],
        "dividend": ["利润分配", "公告"],
    }
    selected: dict[str, dict[str, Any]] = {}
    for key, kws in targets.items():
        item = first_announcement_match(pages, kws)
        if item:
            selected[key] = item
    return selected


def pdf_url_from_adjunct(adjunct_url: str) -> str:
    return "https://static.cninfo.com.cn/" + adjunct_url.lstrip("/")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run stock check pipeline")
    ap.add_argument("code", help="stock code, e.g. 000993")
    ap.add_argument("--name", default="")
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--report-name", default="年度报告")
    ap.add_argument("--use-scrapling-fallback", action="store_true")
    ap.add_argument("--skip-pdftotext", action="store_true")
    args = ap.parse_args()

    run_dir = RUNS / args.code
    raw_dir = run_dir / "raw"
    facts_dir = run_dir / "facts"
    notes_dir = run_dir / "notes"
    final_dir = run_dir / "final"
    for d in (raw_dir, facts_dir, notes_dir, final_dir):
        d.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "code": args.code,
        "steps": [],
        "fallbacks": [],
    }

    f10_path = raw_dir / "f10.html"
    try:
        proc = run_py("fetch_cninfo_f10.py", args.code, "--out", str(f10_path))
        summary["steps"].append({"step": "fetch_f10", "ok": True, "stdout": proc.stdout.strip()})
    except subprocess.CalledProcessError:
        if not args.use_scrapling_fallback:
            raise
        url = f"https://www.cninfo.com.cn/new/disclosure/stock?tabName=data&f002v=001001&stockCode={args.code}&type=info"
        proc = run_py("fetch_with_scrapling.py", url, "--out", str(f10_path))
        summary["steps"].append({"step": "fetch_f10", "ok": True, "stdout": proc.stdout.strip()})
        summary["fallbacks"].append({"step": "fetch_f10", "tool": "scrapling", "url": url})

    meta = extract_meta_from_f10(f10_path.read_text(encoding="utf-8", errors="ignore"))
    if not {"stockCode", "orgId", "plate"}.issubset(meta.keys()):
        raise SystemExit(f"failed to extract f10 meta from {f10_path}: {meta}")
    (facts_dir / "f10_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    proc = run_py(
        "fetch_cninfo_announcements.py",
        args.code,
        meta["orgId"],
        "--column",
        meta["plate"],
        "--plate",
        meta["plate"],
        "--pages",
        str(args.pages),
        "--outdir",
        str(raw_dir),
    )
    summary["steps"].append({"step": "fetch_announcements", "ok": True, "stdout": proc.stdout.strip().splitlines()})

    page_files = [raw_dir / f"announcements_p{i}.json" for i in range(1, args.pages + 1) if (raw_dir / f"announcements_p{i}.json").exists()]
    selected = choose_report_targets(page_files)
    (facts_dir / "selected_announcements.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    annual = None
    for item in selected.values():
        title = str(item.get("announcementTitle", ""))
        if args.report_name in title and item.get("adjunctUrl"):
            annual = item
            break
    if annual is None:
        item = first_announcement_match(page_files, [args.report_name])
        if item and item.get("adjunctUrl"):
            annual = item

    if annual:
        pdf_out = raw_dir / f"{args.code}_{args.report_name}.pdf"
        proc = run_py("fetch_cninfo_pdf.py", annual["adjunctUrl"], "--out", str(pdf_out))
        summary["steps"].append({"step": "fetch_pdf", "ok": True, "stdout": proc.stdout.strip()})
        summary["pdf"] = {
            "announcementTitle": annual.get("announcementTitle"),
            "announcementId": annual.get("announcementId"),
            "adjunctUrl": annual.get("adjunctUrl"),
            "pdfUrl": pdf_url_from_adjunct(annual["adjunctUrl"]),
            "saved": str(pdf_out),
        }
        if not args.skip_pdftotext and Path(PDFTOTEXT).exists():
            txt_out = pdf_out.with_suffix(".txt")
            proc = subprocess.run([PDFTOTEXT, str(pdf_out), str(txt_out)], capture_output=True, text=True)
            summary["steps"].append({
                "step": "pdftotext",
                "ok": proc.returncode == 0,
                "stderr": proc.stderr.strip(),
                "saved": str(txt_out),
            })
            if proc.returncode == 0:
                report_proc = run_py(
                    "generate_stock_report.py",
                    args.code,
                    (args.name or args.code),
                    "--txt",
                    str(txt_out),
                    "--meta",
                    str(facts_dir / "f10_meta.json"),
                    "--selected",
                    str(facts_dir / "selected_announcements.json"),
                    "--outdir",
                    str(final_dir),
                )
                summary["steps"].append({
                    "step": "generate_report",
                    "ok": True,
                    "stdout": report_proc.stdout.strip(),
                })
    else:
        summary["steps"].append({"step": "fetch_pdf", "ok": False, "reason": f"no match for {args.report_name}"})

    out = run_dir / "run_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
