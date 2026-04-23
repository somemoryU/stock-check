#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_SCRIPT="$ROOT/scripts/generate_stock_report.py"
CODE="${1:-600036}"
NAME="${2:-招商银行}"
TXT="$ROOT/runs/$CODE/raw/${CODE}_年度报告.txt"
META="$ROOT/runs/$CODE/facts/f10_meta.json"
SELECTED="$ROOT/runs/$CODE/facts/selected_announcements.json"
OUTDIR="$ROOT/runs/$CODE/final"

if [[ ! -f "$TXT" || ! -f "$META" || ! -f "$SELECTED" ]]; then
  echo "missing sample files for code=$CODE under runs/$CODE" >&2
  exit 1
fi

assert_enabled() {
  echo "[1/3] scoring enabled scenario"
  python3 "$PY_SCRIPT" "$CODE" "$NAME" --txt "$TXT" --meta "$META" --selected "$SELECTED" --outdir "$OUTDIR" >/dev/null
  python3 - "$ROOT" "$CODE" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
code = sys.argv[2]
path = root / "runs" / code / "facts" / "core_metrics.json"
data = json.loads(path.read_text(encoding="utf-8"))
required = ["total_score", "item_scores", "risk_level", "explanations", "confidence", "degraded_reasons"]
missing = [k for k in required if k not in data]
if missing:
    raise SystemExit(f"enabled scenario missing fields: {missing}")
if not isinstance(data["item_scores"], list) or len(data["item_scores"]) < 3:
    raise SystemExit("enabled scenario expects at least 3 item_scores")
if not (0.0 <= float(data["confidence"]) <= 1.0):
    raise SystemExit("enabled scenario confidence out of range")
print(f"enabled ok: total_score={data['total_score']}, risk_level={data['risk_level']}, items={len(data['item_scores'])}")
PY
}

assert_disabled() {
  echo "[2/3] scoring disabled scenario"
  STOCK_CHECK_SCORING_ENABLED=false python3 "$PY_SCRIPT" "$CODE" "$NAME" --txt "$TXT" --meta "$META" --selected "$SELECTED" --outdir "$OUTDIR" >/dev/null
  python3 - "$ROOT" "$CODE" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
code = sys.argv[2]
path = root / "runs" / code / "facts" / "core_metrics.json"
data = json.loads(path.read_text(encoding="utf-8"))
if data.get("item_scores") != []:
    raise SystemExit("disabled scenario expects empty item_scores")
if float(data.get("confidence", -1)) != 0.0:
    raise SystemExit("disabled scenario expects confidence=0.0")
reasons = data.get("degraded_reasons") or []
if "scoring_engine_disabled" not in reasons:
    raise SystemExit("disabled scenario missing degraded reason scoring_engine_disabled")
print(f"disabled ok: total_score={data['total_score']}, risk_level={data['risk_level']}, reasons={reasons}")
PY
}

assert_fail_fast() {
  echo "[3/3] fail-fast scenario"
  local missing_path="/tmp/stock-check-scoring-missing-$$.json"
  rm -f "$missing_path"
  set +e
  output=$(STOCK_CHECK_SCORING_CONFIG="$missing_path" python3 "$PY_SCRIPT" "$CODE" "$NAME" --txt "$TXT" --meta "$META" --selected "$SELECTED" --outdir "$OUTDIR" 2>&1)
  status=$?
  set -e
  if [[ $status -eq 0 ]]; then
    echo "fail-fast scenario expected non-zero exit" >&2
    exit 1
  fi
  if [[ "$output" != *"invalid scoring config: missing override file"* ]]; then
    echo "fail-fast scenario expected missing override message" >&2
    echo "$output" >&2
    exit 1
  fi
  echo "fail-fast ok: status=$status"
}

assert_enabled
assert_disabled
assert_fail_fast

echo "smoke_scoring_phase1 passed for code=$CODE"
