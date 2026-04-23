from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCORING_PATH = ROOT / "config" / "scoring.default.json"
LOCAL_SCORING_PATH = ROOT / "config" / "scoring.local.json"


def _deep_update(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def _parse_bool(raw: str) -> bool:
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off"}:
        return False
    raise SystemExit(f"invalid config: STOCK_CHECK_SCORING_ENABLED should be boolean-like, got {raw}")


def _require(cfg: dict[str, Any], path: tuple[str, ...], expect_type: Any) -> Any:
    ref: Any = cfg
    walked: list[str] = []
    for key in path:
        walked.append(key)
        if not isinstance(ref, dict) or key not in ref:
            raise SystemExit(f"invalid scoring config: missing {'.'.join(walked)}")
        ref = ref[key]
    if not isinstance(ref, expect_type):
        type_name = expect_type.__name__ if isinstance(expect_type, type) else "number"
        raise SystemExit(
            f"invalid scoring config: {'.'.join(path)} should be {type_name}, got {type(ref).__name__}"
        )
    return ref


def validate_scoring_config(cfg: dict[str, Any]) -> None:
    _require(cfg, ("engine", "enabled"), bool)
    _require(cfg, ("engine", "baseline_score"), (int, float))
    risk = _require(cfg, ("risk_levels",), dict)
    if not isinstance(risk.get("low_risk_min"), (int, float)):
        raise SystemExit("invalid scoring config: risk_levels.low_risk_min should be number")
    if not isinstance(risk.get("medium_risk_min"), (int, float)):
        raise SystemExit("invalid scoring config: risk_levels.medium_risk_min should be number")
    if float(risk["medium_risk_min"]) > float(risk["low_risk_min"]):
        raise SystemExit("invalid scoring config: risk_levels.medium_risk_min should be <= low_risk_min")

    rules = _require(cfg, ("rules",), list)
    if not rules:
        raise SystemExit("invalid scoring config: rules should not be empty")

    allowed_directions = {"higher_is_better", "lower_is_better"}
    seen_ids: set[str] = set()
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise SystemExit(f"invalid scoring config: rules[{idx}] should be object")
        for field, typ in [
            ("id", str),
            ("metric", str),
            ("enabled", bool),
            ("weight", (int, float)),
            ("threshold", (int, float)),
            ("direction", str),
            ("explanation_template", str),
        ]:
            val = rule.get(field)
            if not isinstance(val, typ):
                type_name = typ.__name__ if isinstance(typ, type) else "number"
                raise SystemExit(
                    f"invalid scoring config: rules[{idx}].{field} should be {type_name}, got {type(val).__name__}"
                )
        if rule["direction"] not in allowed_directions:
            raise SystemExit(
                f"invalid scoring config: rules[{idx}].direction should be one of {sorted(allowed_directions)}"
            )
        if rule["id"] in seen_ids:
            raise SystemExit(f"invalid scoring config: duplicate rule id {rule['id']}")
        seen_ids.add(rule["id"])


def load_scoring_config() -> dict[str, Any]:
    if not DEFAULT_SCORING_PATH.exists():
        raise SystemExit(f"invalid scoring config: missing default scoring file {DEFAULT_SCORING_PATH}")

    cfg = json.loads(DEFAULT_SCORING_PATH.read_text(encoding="utf-8"))

    configured_path = os.getenv("STOCK_CHECK_SCORING_CONFIG", "").strip()
    override_path = Path(configured_path) if configured_path else LOCAL_SCORING_PATH
    if configured_path and not override_path.exists():
        raise SystemExit(f"invalid scoring config: missing override file {override_path}")
    if override_path.exists():
        override = json.loads(override_path.read_text(encoding="utf-8"))
        cfg = _deep_update(cfg, override)

    raw_enabled = os.getenv("STOCK_CHECK_SCORING_ENABLED", "").strip()
    if raw_enabled:
        cfg.setdefault("engine", {})
        cfg["engine"]["enabled"] = _parse_bool(raw_enabled)

    validate_scoring_config(cfg)
    return cfg
