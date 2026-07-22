"""Per-family per-day feature extraction — streaming, stdlib-only, deterministic.

Each extractor reads one committed tape day (``tape/<family>/dt=YYYY-MM-DD.jsonl``)
line-by-line (never loads a file into memory — orderbook_depth days run to tens of MB)
and emits small per-(series, dt) aggregate rows. Aggregates are what the screens read;
they are committed under ``reports/observatory/daily/<family>/dt=*.json`` so a cloud
run only processes tape days it has not summarized yet.

Honesty rules carried over from the collectors:
  * every aggregate row carries the price_source_tag(s) of the quotes it summarizes —
    a row built on anything other than real_ask/real_bid can never feed a fee-cleared
    pattern (core.source_tag.is_fillable gates that downstream);
  * malformed lines are COUNTED (``n_bad_lines``), never silently dropped — a decode
    failure lowers trust in the day, it does not shrink the denominator invisibly;
  * per ticker (or event_ticker) only the LAST capture of the day enters the medians,
    so a day with 24 hourly passes does not get 24x the weight of a day with one.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.io import REPO_ROOT
from core.source_tag import tag_or_synthetic

TAPE_ROOT = REPO_ROOT / "tape"
DAILY_ROOT = REPO_ROOT / "reports" / "observatory" / "daily"

PILOT_FAMILIES = ("universe_sweep", "orderbook_depth", "sports_pairs")

# The depth tape tags its bid side "real_bid" — the bid-side twin of real_ask,
# absent from core.source_tag.SOURCE_TAGS (which is ask/settlement-oriented).
# tag_or_synthetic would coerce it to "synthetic", destroying true provenance,
# so normalize locally: known tags pass through, everything else -> synthetic.
_KNOWN_TAGS = frozenset({"real_ask", "real_bid", "broker_truth", "midpoint", "synthetic"})


def _norm_tag(tag) -> str:
    return tag if tag in _KNOWN_TAGS else tag_or_synthetic(tag)

# Cross-section unit: the series prefix embedded in every Kalshi ticker
# (e.g. "KXBTC-26JUL0621-T71799.99" -> "KXBTC").


def series_of(ticker: str) -> str:
    return ticker.split("-", 1)[0] if ticker else "UNKNOWN"


def _median(vals: List[float]) -> Optional[float]:
    return round(statistics.median(vals), 6) if vals else None


def _last_per_key(rows: Iterable[Tuple[str, str, dict]]) -> Dict[str, dict]:
    """(key, captured_at, obs) -> {key: obs of max captured_at}. Deterministic:
    ties on captured_at resolve to the later line in file order."""
    best: Dict[str, Tuple[str, dict]] = {}
    for key, cap, obs in rows:
        if key not in best or cap >= best[key][0]:
            best[key] = (cap, obs)
    return {k: v[1] for k, v in best.items()}


def _iter_jsonl(path: Path) -> Iterable[Tuple[Optional[dict], bool]]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obs = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                yield None, False
                continue
            if isinstance(obs, dict):
                yield obs, True
            else:  # valid JSON but not an object — still a bad line, still counted
                yield None, False


def _two_sided(yes_bid: Optional[float], yes_ask: Optional[float]) -> bool:
    return (
        yes_bid is not None
        and yes_ask is not None
        and 0.0 < yes_bid
        and yes_bid < yes_ask
        and yes_ask < 1.0
    )


def extract_universe_sweep(path: Path) -> List[Dict[str, Any]]:
    n_bad = 0
    per_ticker: List[Tuple[str, str, dict]] = []
    for obs, ok in _iter_jsonl(path):
        if not ok:
            n_bad += 1
            continue
        t = obs.get("ticker")
        if not t:
            n_bad += 1
            continue
        per_ticker.append((t, obs.get("captured_at") or "", obs))
    last = _last_per_key(per_ticker)

    by_series: Dict[str, List[dict]] = {}
    tags: Dict[str, set] = {}
    for t, obs in last.items():
        s = series_of(t)
        by_series.setdefault(s, []).append(obs)
        tags.setdefault(s, set()).add(tag_or_synthetic(obs.get("price_source_tag")))

    rows = []
    for s in sorted(by_series):
        markets = by_series[s]
        spreads, mids, vols = [], [], []
        n_two = 0
        for m in markets:
            ya, yb = m.get("yes_ask"), m.get("yes_bid")
            if _two_sided(yb, ya):
                n_two += 1
                spreads.append(ya - yb)
                mids.append((ya + yb) / 2.0)
            v = m.get("volume_24h")
            if isinstance(v, (int, float)):
                vols.append(float(v))
        rows.append({
            "family": "universe_sweep",
            "series": s,
            "n_markets": len(markets),
            "n_two_sided": n_two,
            "two_sided_share": round(n_two / len(markets), 6) if markets else None,
            "median_spread": _median(spreads),
            "median_mid": _median(mids),
            "total_volume_24h": round(sum(vols), 2),
            "price_source_tags": sorted(tags[s]),
            "n_bad_lines": n_bad,
        })
    return rows


def extract_orderbook_depth(path: Path) -> List[Dict[str, Any]]:
    n_bad = 0
    per_ticker: List[Tuple[str, str, dict]] = []
    for obs, ok in _iter_jsonl(path):
        if not ok:
            n_bad += 1
            continue
        t = obs.get("ticker")
        if not t:
            n_bad += 1
            continue
        # Keep only the small fields — never retain the full ladder rows in memory.
        no_bids = obs.get("no_bids") or []
        yes_bids = obs.get("yes_bids") or []
        slim = {
            "best_yes_ask": obs.get("best_yes_ask"),
            "best_yes_bid": obs.get("best_yes_bid"),
            "depth": obs.get("depth"),
            "touch_queue": (no_bids[0][1] if no_bids else None),
            "touch_queue_yes": (yes_bids[0][1] if yes_bids else None),
            "tags": obs.get("price_source_tags") or {},
        }
        per_ticker.append((t, obs.get("captured_at") or "", slim))
    last = _last_per_key(per_ticker)

    by_series: Dict[str, List[dict]] = {}
    tags: Dict[str, set] = {}
    for t, obs in last.items():
        s = series_of(t)
        by_series.setdefault(s, []).append(obs)
        for v in obs["tags"].values():
            tags.setdefault(s, set()).add(_norm_tag(v))

    rows = []
    for s in sorted(by_series):
        snaps = by_series[s]
        spreads, mids, depths, queues = [], [], [], []
        n_two = 0
        for m in snaps:
            ya, yb = m["best_yes_ask"], m["best_yes_bid"]
            if _two_sided(yb, ya):
                n_two += 1
                spreads.append(ya - yb)
                mids.append((ya + yb) / 2.0)
            if isinstance(m["depth"], (int, float)):
                depths.append(float(m["depth"]))
            tq = m["touch_queue"]
            if isinstance(tq, (int, float)):
                queues.append(float(tq))
        rows.append({
            "family": "orderbook_depth",
            "series": s,
            "n_markets": len(snaps),
            "n_two_sided": n_two,
            "two_sided_share": round(n_two / len(snaps), 6) if snaps else None,
            "median_spread": _median(spreads),
            "median_mid": _median(mids),
            "median_depth": _median(depths),
            "median_touch_queue": _median(queues),
            "price_source_tags": sorted(tags.get(s, {"synthetic"})),
            "n_bad_lines": n_bad,
        })
    return rows


def extract_sports_pairs(path: Path) -> List[Dict[str, Any]]:
    n_bad = 0
    per_event: List[Tuple[str, str, dict]] = []
    for obs, ok in _iter_jsonl(path):
        if not ok:
            n_bad += 1
            continue
        e = obs.get("event_ticker")
        if not e:
            n_bad += 1
            continue
        per_event.append((e, obs.get("captured_at") or "", obs))
    last = _last_per_key(per_event)

    by_series: Dict[str, List[dict]] = {}
    tags: Dict[str, set] = {}
    for e, obs in last.items():
        s = obs.get("sport_series") or series_of(e)
        by_series.setdefault(s, []).append(obs)
        tags.setdefault(s, set()).add(tag_or_synthetic(obs.get("price_source_tag")))

    rows = []
    for s in sorted(by_series):
        events = by_series[s]
        overs = [e["overround"] for e in events if isinstance(e.get("overround"), (int, float))]
        n_complete = sum(1 for e in events if e.get("completeness_ok") is True)
        rows.append({
            "family": "sports_pairs",
            "series": s,
            "n_events": len(events),
            "median_overround": _median(overs),
            "completeness_rate": round(n_complete / len(events), 6) if events else None,
            "price_source_tags": sorted(tags[s]),
            "n_bad_lines": n_bad,
        })
    return rows


EXTRACTORS = {
    "universe_sweep": extract_universe_sweep,
    "orderbook_depth": extract_orderbook_depth,
    "sports_pairs": extract_sports_pairs,
}


def tape_days(family: str, tape_root: Path = TAPE_ROOT) -> List[str]:
    """Sorted dt strings for which a committed tape day exists."""
    fam_dir = tape_root / family
    if not fam_dir.is_dir():
        return []
    out = []
    for p in sorted(fam_dir.glob("dt=*.jsonl")):
        out.append(p.stem.split("=", 1)[1])
    return out


def summary_path(family: str, dt: str, daily_root: Path = DAILY_ROOT) -> Path:
    return daily_root / family / "dt={}.json".format(dt)


def build_day(family: str, dt: str, tape_root: Path = TAPE_ROOT,
              daily_root: Path = DAILY_ROOT, force: bool = False) -> Optional[Path]:
    """Summarize one tape day to its committed daily aggregate. Returns the path
    written, or None if the summary already existed (and force is False)."""
    out = summary_path(family, dt, daily_root)
    if out.exists() and not force:
        return None
    src = tape_root / family / "dt={}.jsonl".format(dt)
    rows = EXTRACTORS[family](src)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"family": family, "dt": dt, "schema_version": "observatory_daily.v1",
               "rows": rows}
    out.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    return out


def load_day(family: str, dt: str, daily_root: Path = DAILY_ROOT) -> List[Dict[str, Any]]:
    p = summary_path(family, dt, daily_root)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))["rows"]
