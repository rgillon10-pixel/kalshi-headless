"""Structured report writer + tiny data cache. Reports are the audit trail."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"
CONFIG = REPO_ROOT / "config"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default(o: Any):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if is_dataclass(o):
        return asdict(o)
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def write_report(rel_stem: str, payload: Dict[str, Any], *, md_summary: str = "") -> Path:
    """Write reports/<rel_stem>.json (+ .md if md_summary given). Returns json path."""
    json_path = REPORTS / f"{rel_stem}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, default=_default))
    if md_summary:
        (REPORTS / f"{rel_stem}.md").write_text(md_summary)
    return json_path


def cache_path(*parts: str) -> Path:
    p = DATA_RAW.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
