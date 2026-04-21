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


def title_matches(title: str, keywords: list[str], exclude_keywords: list[str] | None = None) -> bool:
    low = title.lower()
    if exclude_keywords and any(k.lower() in low for k in exclude_keywords):
        return False
    return all(k.lower() in low for k in keywords)


def first_announcement_match(
    pages: list[Path],
    keywords: list[str],
    *,
    exclude_keywords: list[str] | None = None,
) -> dict[str, Any] | None:
    for page in pages:
        data = load_json(page)
        for item in (data.get("announcements") or []):
            title = str(item.get("announcementTitle", ""))
            if title_matches(title, keywords, exclude_keywords):
                return item
    return None


def best_annual_report(pages: list[Path], report_name: str) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for page in pages:
        data = load_json(page)
        for item in (data.get("announcements") or []):
            title = str(item.get("announcementTitle", ""))
            if title_matches(title, [report_name], ["半年度"]):
                candidates.append(item)
    if not candidates:
        return None

    # prefer full annual report over summary
    full = [c for c in candidates if "摘要" not in str(c.get("announcementTitle", ""))]
    if full:
        return full[0]
    return candidates[0]


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
        if key == "annual_report":
            item = best_annual_report(pages, kws[0])
        else:
            item = first_announcement_match(pages, kws)
        if item:
            selected[key] = item
    return selected


def pdf_url_from_adjunct(adjunct_url: str) -> str:
    return "https://static.cninfo.com.cn/" + adjunct_url.lstrip("/")


def fetch_announcement_pages(code: str, meta: dict[str, str], raw_dir: Path, start_page: int, pages: int) -> list[str]:
    proc = run_py(
        "fetch_cninfo_announcements.py",
        code,
        meta["orgId"],
        "--column",
        meta["plate"],
        "--plate",
        meta["plate"],
        "--pageNum",
        str(start_page),
        "--pages",
        str(pages),
        "--outdir",
        str(raw_dir),
    )
    return proc.stdout.strip().splitlines()


def main() -> None:
    ap = argparse.ArgumentParser(description="Run stock check pipeline")
    ap.add_argument("code", help="stock code, e.g. 000993")
    ap.add_argument("--name", default="")
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--max-pages", type=int, default=12)
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

    page_logs: list[str] = []
    fetched_upto = 0
    batch = max(1, args.pages)
    annual = None
    selected: dict[str, dict[str, Any]] = {}

    while fetched_upto < args.max_pages:
        start_page = fetched_upto + 1
        pages_to_fetch = min(batch, args.max_pages - fetched_upto)
        page_logs.extend(fetch_announcement_pages(args.code, meta, raw_dir, start_page, pages_to_fetch))
        fetched_upto += pages_to_fetch

        page_files = [raw_dir / f"announcements_p{i}.json" for i in range(1, fetched_upto + 1) if (raw_dir / f"announcements_p{i}.json").exists()]
        selected = choose_report_targets(page_files)
        annual = best_annual_report(page_files, args.report_name)
        if annual and annual.get("adjunctUrl"):
            break

        counts = []
        for i in range(start_page, fetched_upto + 1):
            p = raw_dir / f"announcements_p{i}.json"
            if p.exists():
                data = load_json(p)
                counts.append(len(data.get("announcements") or []))
        if counts and all(c == 0 for c in counts):
            break

    summary["steps"].append({
        "step": "fetch_announcements",
        "ok": True,
        "stdout": page_logs,
        "pagesFetched": fetched_upto,
    })

    (facts_dir / "selected_announcements.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    if annual is None:
        annual = selected.get("annual_report")

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
        summary["steps"].append({
            "step": "fetch_pdf",
            "ok": False,
            "reason": f"no match for {args.report_name}",
            "pagesFetched": fetched_upto,
        })

    out = run_dir / "run_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
